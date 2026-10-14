package jobs

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

const jobID = "05cf52b9-bb49-46a8-948f-4a1e51a3fa0c"

func runAgainst(t *testing.T, handler http.HandlerFunc) (Report, error) {
	t.Helper()
	server := httptest.NewServer(handler)
	defer server.Close()
	runner := &HTTPRunner{BaseURL: server.URL + "/actuator/forecastjobs/", Client: server.Client()}
	return runner.Run(context.Background(), Message{JobID: jobID, TraceParent: "00-abc-def-01"})
}

func TestRunPostsTheJobAndReadsTheReport(t *testing.T) {
	report, err := runAgainst(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/actuator/forecastjobs/"+jobID {
			t.Errorf("got %s %s", r.Method, r.URL.Path)
		}
		if r.Header.Get("traceparent") != "00-abc-def-01" {
			t.Errorf("trace context not forwarded: %q", r.Header.Get("traceparent"))
		}
		_, _ = w.Write([]byte(`{"job_id":"` + jobID + `","outcome":"ran","status":"SUCCEEDED","attempts":1}`))
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if report != (Report{JobID: jobID, Outcome: "ran", Status: "SUCCEEDED", Attempts: 1}) {
		t.Fatalf("report %+v", report)
	}
}

func TestServerErrorsAndThrottlingAreRetryable(t *testing.T) {
	for _, status := range []int{http.StatusServiceUnavailable, http.StatusInternalServerError, http.StatusTooManyRequests} {
		_, err := runAgainst(t, func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(status) })
		if !IsRetryable(err) {
			t.Fatalf("status %d: expected a retryable error, got %v", status, err)
		}
	}
}

func TestClientErrorsAreNotRetried(t *testing.T) {
	for _, status := range []int{http.StatusBadRequest, http.StatusNotFound} {
		_, err := runAgainst(t, func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(status) })
		if err == nil || IsRetryable(err) {
			t.Fatalf("status %d: expected a permanent error, got %v", status, err)
		}
	}
}

func TestAnUnreadableReportIsNotRetried(t *testing.T) {
	_, err := runAgainst(t, func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write([]byte(`<html>`)) })
	if err == nil || IsRetryable(err) {
		t.Fatalf("expected a permanent error, got %v", err)
	}
}

func TestAnUnreachableBackendIsRetryable(t *testing.T) {
	server := httptest.NewServer(http.NotFoundHandler())
	server.Close()
	runner := &HTTPRunner{BaseURL: server.URL, Client: &http.Client{Timeout: time.Second}}

	if _, err := runner.Run(context.Background(), Message{JobID: jobID}); !IsRetryable(err) {
		t.Fatalf("expected a retryable error, got %v", err)
	}
}

func TestATimedOutRunIsRetryable(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		<-r.Context().Done()
	}))
	defer server.Close()
	runner := &HTTPRunner{BaseURL: server.URL, Client: server.Client()}
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	if _, err := runner.Run(ctx, Message{JobID: jobID}); !IsRetryable(err) {
		t.Fatalf("expected a retryable error, got %v", err)
	}
}
