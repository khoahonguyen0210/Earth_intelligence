//go:build integration

package jobs

import (
	"context"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/segmentio/kafka-go"
)

func brokers() []string {
	if value := os.Getenv("KAFKA_BROKERS"); value != "" {
		return strings.Split(value, ",")
	}
	return []string{"localhost:9094"}
}

func createTopic(t *testing.T, topic string) {
	t.Helper()
	conn, err := kafka.Dial("tcp", brokers()[0])
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer conn.Close()
	controller, err := conn.Controller()
	if err != nil {
		t.Fatalf("controller: %v", err)
	}
	controllerConn, err := kafka.Dial("tcp", net.JoinHostPort(controller.Host, strconv.Itoa(controller.Port)))
	if err != nil {
		t.Fatalf("dial controller: %v", err)
	}
	defer controllerConn.Close()
	if err := controllerConn.CreateTopics(kafka.TopicConfig{Topic: topic, NumPartitions: 1, ReplicationFactor: 1}); err != nil {
		t.Fatalf("create topic: %v", err)
	}
}

func publish(t *testing.T, topic, id string) {
	t.Helper()
	writer := &kafka.Writer{Addr: kafka.TCP(brokers()...), Topic: topic, RequiredAcks: kafka.RequireAll, BatchTimeout: 10 * time.Millisecond}
	defer writer.Close()
	if err := writer.WriteMessages(context.Background(), kafka.Message{Key: []byte(id), Value: []byte(`{"job_id":"` + id + `"}`)}); err != nil {
		t.Fatalf("publish: %v", err)
	}
}

type recordingBackend struct {
	mu   sync.Mutex
	seen []string
}

func (b *recordingBackend) ids() []string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return append([]string{}, b.seen...)
}

func consumeUntil(t *testing.T, topic, group, runURL string, backend *recordingBackend, want int) {
	t.Helper()
	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers: brokers(), GroupID: group, Topic: topic, MinBytes: 1, MaxBytes: 1 << 20,
		MaxWait: 200 * time.Millisecond, StartOffset: kafka.FirstOffset,
	})
	defer reader.Close()
	consumer := &Consumer{
		Reader:     reader,
		Runner:     &HTTPRunner{BaseURL: runURL, Client: &http.Client{Timeout: 5 * time.Second}},
		Logger:     slog.New(slog.NewTextHandler(io.Discard, nil)),
		RunTimeout: 5 * time.Second,
		Backoff:    Backoff{Min: 10 * time.Millisecond, Max: 50 * time.Millisecond},
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- consumer.Run(ctx) }()
	deadline := time.Now().Add(60 * time.Second)
	for len(backend.ids()) < want && time.Now().Before(deadline) {
		time.Sleep(50 * time.Millisecond)
	}
	time.Sleep(500 * time.Millisecond)
	cancel()
	if err := <-done; err != nil {
		t.Fatalf("consumer: %v", err)
	}
}

func TestJobsFromKafkaReachTheBackendAndAreCommitted(t *testing.T) {
	suffix := strconv.FormatInt(time.Now().UnixNano(), 16)
	topic, group := "forecast-jobs-go-itest-"+suffix, "forecast-workers-go-itest-"+suffix
	createTopic(t, topic)

	backend := &recordingBackend{}
	unavailableOnce := true
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		backend.mu.Lock()
		defer backend.mu.Unlock()
		if unavailableOnce {
			unavailableOnce = false
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		id := r.URL.Path[strings.LastIndex(r.URL.Path, "/")+1:]
		backend.seen = append(backend.seen, id)
		_, _ = w.Write([]byte(`{"job_id":"` + id + `","outcome":"ran","status":"SUCCEEDED","attempts":1}`))
	}))
	defer server.Close()

	first, second := "aaaaaaaa-0000-0000-0000-000000000001", "aaaaaaaa-0000-0000-0000-000000000002"
	publish(t, topic, first)
	consumeUntil(t, topic, group, server.URL, backend, 1)

	publish(t, topic, second)
	consumeUntil(t, topic, group, server.URL, backend, 2)

	if got := backend.ids(); len(got) != 2 || got[0] != first || got[1] != second {
		t.Fatalf("backend saw %v; the first job must run once and the second once", got)
	}
}
