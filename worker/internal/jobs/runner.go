package jobs

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

const maxResponseBytes = 1 << 20

type Report struct {
	JobID    string `json:"job_id"`
	Outcome  string `json:"outcome"`
	Status   string `json:"status"`
	Attempts int    `json:"attempts"`
}

type Runner interface {
	Run(ctx context.Context, message Message) (Report, error)
}

type RetryableError struct {
	Err error
}

func (e *RetryableError) Error() string {
	return e.Err.Error()
}

func (e *RetryableError) Unwrap() error {
	return e.Err
}

func IsRetryable(err error) bool {
	var retryable *RetryableError
	return errors.As(err, &retryable)
}

type HTTPRunner struct {
	BaseURL string
	Client  *http.Client
}

func (r *HTTPRunner) Run(ctx context.Context, message Message) (Report, error) {
	target := strings.TrimRight(r.BaseURL, "/") + "/" + url.PathEscape(message.JobID)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, target, nil)
	if err != nil {
		return Report{}, fmt.Errorf("build request for job %s: %w", message.JobID, err)
	}
	if message.TraceParent != "" {
		request.Header.Set("traceparent", message.TraceParent)
	}

	response, err := r.Client.Do(request)
	if err != nil {
		return Report{}, &RetryableError{Err: fmt.Errorf("call backend for job %s: %w", message.JobID, err)}
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes))
	if err != nil {
		return Report{}, &RetryableError{Err: fmt.Errorf("read backend response for job %s: %w", message.JobID, err)}
	}

	switch {
	case response.StatusCode == http.StatusOK:
		var report Report
		if err := json.Unmarshal(body, &report); err != nil || report.Outcome == "" {
			return Report{}, fmt.Errorf("backend returned an unreadable report for job %s: %s", message.JobID, body)
		}
		return report, nil
	case response.StatusCode == http.StatusTooManyRequests || response.StatusCode >= 500:
		return Report{}, &RetryableError{Err: fmt.Errorf("backend unavailable for job %s: %d %s",
			message.JobID, response.StatusCode, strings.TrimSpace(string(body)))}
	default:
		return Report{}, fmt.Errorf("backend rejected job %s: %d %s",
			message.JobID, response.StatusCode, strings.TrimSpace(string(body)))
	}
}
