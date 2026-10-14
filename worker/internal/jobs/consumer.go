package jobs

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/segmentio/kafka-go"
)

type Reader interface {
	FetchMessage(ctx context.Context) (kafka.Message, error)
	CommitMessages(ctx context.Context, messages ...kafka.Message) error
}

type DeadLetters interface {
	WriteMessages(ctx context.Context, messages ...kafka.Message) error
}

type Backoff struct {
	Min time.Duration
	Max time.Duration
}

type Consumer struct {
	Reader      Reader
	Runner      Runner
	DeadLetters DeadLetters
	Logger      *slog.Logger
	RunTimeout  time.Duration
	Backoff     Backoff
	Sleep       func(ctx context.Context, d time.Duration) error
}

func (c *Consumer) Run(ctx context.Context) error {
	for {
		message, err := c.Reader.FetchMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return fmt.Errorf("fetch message: %w", err)
		}
		if err := c.handle(ctx, message); err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
	}
}

func (c *Consumer) handle(ctx context.Context, message kafka.Message) error {
	log := c.Logger.With("partition", message.Partition, "offset", message.Offset)
	job, err := Decode(message.Value)
	if err != nil {
		log.Error("message dead-lettered", "event", "job_message_invalid", "error", err)
		return c.deadLetter(ctx, message, err)
	}
	log = log.With("job_id", job.JobID)

	delay := c.Backoff.Min
	for attempt := 1; ; attempt++ {
		started := time.Now()
		report, err := c.runOnce(ctx, job)
		if err == nil {
			log.Info("job handled", "event", "job_handled", "outcome", report.Outcome, "status", report.Status,
				"attempts", report.Attempts, "duration_ms", time.Since(started).Milliseconds())
			return c.commit(ctx, message)
		}
		if !IsRetryable(err) {
			log.Error("job dead-lettered", "event", "job_rejected", "error", err)
			return c.deadLetter(ctx, message, err)
		}
		log.Warn("backend unavailable, retrying", "event", "job_retry", "attempt", attempt,
			"retry_in_ms", delay.Milliseconds(), "error", err)
		if err := c.sleep(ctx, delay); err != nil {
			return err
		}
		delay = min(delay*2, c.Backoff.Max)
	}
}

func (c *Consumer) runOnce(ctx context.Context, job Message) (Report, error) {
	runCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), c.RunTimeout)
	defer cancel()
	return c.Runner.Run(runCtx, job)
}

func (c *Consumer) deadLetter(ctx context.Context, message kafka.Message, cause error) error {
	if c.DeadLetters != nil {
		letter := kafka.Message{
			Key:   message.Key,
			Value: message.Value,
			Headers: append(append([]kafka.Header{}, message.Headers...),
				kafka.Header{Key: "error", Value: []byte(cause.Error())},
				kafka.Header{Key: "source_topic", Value: []byte(message.Topic)},
				kafka.Header{Key: "source_offset", Value: []byte(fmt.Sprint(message.Offset))},
			),
		}
		if err := c.DeadLetters.WriteMessages(context.WithoutCancel(ctx), letter); err != nil {
			return fmt.Errorf("write dead letter: %w", err)
		}
	}
	return c.commit(ctx, message)
}

func (c *Consumer) commit(ctx context.Context, message kafka.Message) error {
	if err := c.Reader.CommitMessages(context.WithoutCancel(ctx), message); err != nil {
		return fmt.Errorf("commit offset %d: %w", message.Offset, err)
	}
	return nil
}

func (c *Consumer) sleep(ctx context.Context, d time.Duration) error {
	if c.Sleep != nil {
		return c.Sleep(ctx, d)
	}
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
