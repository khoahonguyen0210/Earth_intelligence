package jobs

import (
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
)

var ErrInvalidMessage = errors.New("invalid job message")

var jobIDPattern = regexp.MustCompile(`^[0-9a-fA-F-]{1,64}$`)

type Message struct {
	JobID       string `json:"job_id"`
	EnqueuedAt  string `json:"enqueued_at,omitempty"`
	TraceParent string `json:"trace_parent,omitempty"`
}

func Decode(value []byte) (Message, error) {
	var message Message
	if err := json.Unmarshal(value, &message); err != nil {
		return Message{}, fmt.Errorf("%w: %v", ErrInvalidMessage, err)
	}
	if !jobIDPattern.MatchString(message.JobID) {
		return Message{}, fmt.Errorf("%w: job_id %q", ErrInvalidMessage, message.JobID)
	}
	return message, nil
}
