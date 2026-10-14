package jobs

import (
	"errors"
	"strings"
	"testing"
)

func TestDecodeReadsTheBackendMessage(t *testing.T) {
	message, err := Decode([]byte(`{"job_id":"05cf52b9-bb49-46a8-948f-4a1e51a3fa0c","enqueued_at":"2026-10-14T03:32:52Z","trace_parent":"00-abc-def-01"}`))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if message.JobID != "05cf52b9-bb49-46a8-948f-4a1e51a3fa0c" || message.TraceParent != "00-abc-def-01" {
		t.Fatalf("decoded %+v", message)
	}
}

func TestDecodeRejectsBadMessages(t *testing.T) {
	for name, value := range map[string]string{
		"not json":       `job-1`,
		"no job id":      `{"enqueued_at":"2026-10-14T03:32:52Z"}`,
		"path traversal": `{"job_id":"../../etc/passwd"}`,
		"too long":       `{"job_id":"` + strings.Repeat("a", 65) + `"}`,
		"wrong type":     `{"job_id":42}`,
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := Decode([]byte(value)); !errors.Is(err, ErrInvalidMessage) {
				t.Fatalf("expected ErrInvalidMessage, got %v", err)
			}
		})
	}
}
