package jobs

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"sync"
	"testing"
	"time"

	"github.com/segmentio/kafka-go"
)

type fakeReader struct {
	mu        sync.Mutex
	pending   []kafka.Message
	committed []int64
	commitErr error
}

func (r *fakeReader) FetchMessage(ctx context.Context) (kafka.Message, error) {
	r.mu.Lock()
	if len(r.pending) > 0 {
		message := r.pending[0]
		r.pending = r.pending[1:]
		r.mu.Unlock()
		return message, nil
	}
	r.mu.Unlock()
	<-ctx.Done()
	return kafka.Message{}, ctx.Err()
}

func (r *fakeReader) CommitMessages(_ context.Context, messages ...kafka.Message) error {
	if r.commitErr != nil {
		return r.commitErr
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	for _, message := range messages {
		r.committed = append(r.committed, message.Offset)
	}
	return nil
}

func (r *fakeReader) commits() []int64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	return append([]int64{}, r.committed...)
}

type fakeDeadLetters struct {
	mu      sync.Mutex
	letters []kafka.Message
}

func (d *fakeDeadLetters) WriteMessages(_ context.Context, messages ...kafka.Message) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.letters = append(d.letters, messages...)
	return nil
}

type scriptedRunner struct {
	mu      sync.Mutex
	results []error
	calls   []string
}

func (r *scriptedRunner) Run(_ context.Context, message Message) (Report, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.calls = append(r.calls, message.JobID)
	var err error
	if len(r.results) > 0 {
		err = r.results[0]
		r.results = r.results[1:]
	}
	if err != nil {
		return Report{}, err
	}
	return Report{JobID: message.JobID, Outcome: "ran", Status: "SUCCEEDED", Attempts: 1}, nil
}

func jobMessage(offset int64, value string) kafka.Message {
	return kafka.Message{Topic: "forecast-jobs", Offset: offset, Key: []byte("k"), Value: []byte(value)}
}

func valid(offset int64) kafka.Message {
	return jobMessage(offset, `{"job_id":"`+jobID+`"}`)
}

type harness struct {
	reader  *fakeReader
	runner  *scriptedRunner
	letters *fakeDeadLetters
	sleeps  []time.Duration
}

func newConsumer(h *harness) *Consumer {
	return &Consumer{
		Reader:      h.reader,
		Runner:      h.runner,
		DeadLetters: h.letters,
		Logger:      slog.New(slog.NewTextHandler(io.Discard, nil)),
		RunTimeout:  time.Second,
		Backoff:     Backoff{Min: 100 * time.Millisecond, Max: 300 * time.Millisecond},
		Sleep: func(ctx context.Context, d time.Duration) error {
			h.sleeps = append(h.sleeps, d)
			return ctx.Err()
		},
	}
}

func runUntilIdle(t *testing.T, consumer *Consumer, reader *fakeReader, wantCommits int) error {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- consumer.Run(ctx) }()
	deadline := time.Now().Add(2 * time.Second)
	for len(reader.commits()) < wantCommits && time.Now().Before(deadline) {
		time.Sleep(5 * time.Millisecond)
	}
	cancel()
	return <-done
}

func TestAHandledJobIsCommitted(t *testing.T) {
	h := &harness{reader: &fakeReader{pending: []kafka.Message{valid(7), valid(8)}}, runner: &scriptedRunner{}, letters: &fakeDeadLetters{}}

	if err := runUntilIdle(t, newConsumer(h), h.reader, 2); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := h.reader.commits(); len(got) != 2 || got[0] != 7 || got[1] != 8 {
		t.Fatalf("committed %v", got)
	}
	if len(h.letters.letters) != 0 {
		t.Fatalf("unexpected dead letters")
	}
}

func TestAnUnavailableBackendIsRetriedWithGrowingBackoffBeforeCommitting(t *testing.T) {
	unavailable := &RetryableError{Err: errors.New("503")}
	h := &harness{
		reader:  &fakeReader{pending: []kafka.Message{valid(3)}},
		runner:  &scriptedRunner{results: []error{unavailable, unavailable, unavailable, nil}},
		letters: &fakeDeadLetters{},
	}

	if err := runUntilIdle(t, newConsumer(h), h.reader, 1); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(h.runner.calls) != 4 {
		t.Fatalf("expected 4 calls, got %d", len(h.runner.calls))
	}
	want := []time.Duration{100 * time.Millisecond, 200 * time.Millisecond, 300 * time.Millisecond}
	for i, d := range want {
		if h.sleeps[i] != d {
			t.Fatalf("backoff %v, want %v", h.sleeps, want)
		}
	}
	if got := h.reader.commits(); len(got) != 1 || got[0] != 3 {
		t.Fatalf("committed %v", got)
	}
}

func TestAnInvalidMessageIsDeadLetteredAndCommitted(t *testing.T) {
	h := &harness{reader: &fakeReader{pending: []kafka.Message{jobMessage(5, `not json`)}}, runner: &scriptedRunner{}, letters: &fakeDeadLetters{}}

	if err := runUntilIdle(t, newConsumer(h), h.reader, 1); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(h.runner.calls) != 0 {
		t.Fatalf("the runner must not be called for an invalid message")
	}
	if len(h.letters.letters) != 1 || string(h.letters.letters[0].Value) != "not json" {
		t.Fatalf("dead letters %v", h.letters.letters)
	}
	headers := map[string]string{}
	for _, header := range h.letters.letters[0].Headers {
		headers[header.Key] = string(header.Value)
	}
	if headers["source_topic"] != "forecast-jobs" || headers["source_offset"] != "5" || headers["error"] == "" {
		t.Fatalf("headers %v", headers)
	}
	if got := h.reader.commits(); len(got) != 1 || got[0] != 5 {
		t.Fatalf("committed %v", got)
	}
}

func TestARejectedJobIsDeadLetteredWithoutRetrying(t *testing.T) {
	h := &harness{
		reader:  &fakeReader{pending: []kafka.Message{valid(9)}},
		runner:  &scriptedRunner{results: []error{errors.New("backend rejected job: 400")}},
		letters: &fakeDeadLetters{},
	}

	if err := runUntilIdle(t, newConsumer(h), h.reader, 1); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(h.runner.calls) != 1 || len(h.sleeps) != 0 {
		t.Fatalf("calls %d sleeps %d", len(h.runner.calls), len(h.sleeps))
	}
	if len(h.letters.letters) != 1 {
		t.Fatalf("expected one dead letter")
	}
}

func TestShutdownDuringBackoffLeavesTheMessageUncommitted(t *testing.T) {
	h := &harness{
		reader:  &fakeReader{pending: []kafka.Message{valid(1)}},
		runner:  &scriptedRunner{results: []error{&RetryableError{Err: errors.New("503")}}},
		letters: &fakeDeadLetters{},
	}
	consumer := newConsumer(h)
	ctx, cancel := context.WithCancel(context.Background())
	consumer.Sleep = func(context.Context, time.Duration) error {
		cancel()
		return context.Canceled
	}

	if err := consumer.Run(ctx); err != nil {
		t.Fatalf("shutdown should not be an error: %v", err)
	}
	if got := h.reader.commits(); len(got) != 0 {
		t.Fatalf("committed %v", got)
	}
}

func TestACommitFailureStopsTheConsumer(t *testing.T) {
	h := &harness{
		reader:  &fakeReader{pending: []kafka.Message{valid(2)}, commitErr: errors.New("group rebalanced")},
		runner:  &scriptedRunner{},
		letters: &fakeDeadLetters{},
	}

	if err := newConsumer(h).Run(context.Background()); err == nil {
		t.Fatalf("expected the commit failure to stop the consumer")
	}
}
