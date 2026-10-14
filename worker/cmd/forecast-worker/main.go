package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/segmentio/kafka-go"

	"github.com/khoahonguyen0210/Earth_intelligence/worker/internal/jobs"
)

type config struct {
	brokers     []string
	topic       string
	group       string
	deadLetters string
	runURL      string
	concurrency int
	runTimeout  time.Duration
	healthAddr  string
}

func env(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

func loadConfig() (config, error) {
	concurrency, err := strconv.Atoi(env("WORKER_CONCURRENCY", "2"))
	if err != nil || concurrency < 1 {
		return config{}, fmt.Errorf("WORKER_CONCURRENCY must be a positive integer")
	}
	runTimeout, err := time.ParseDuration(env("RUN_TIMEOUT", "15m"))
	if err != nil || runTimeout <= 0 {
		return config{}, fmt.Errorf("RUN_TIMEOUT must be a positive duration such as 15m")
	}
	return config{
		brokers:     strings.Split(env("KAFKA_BROKERS", "localhost:9094"), ","),
		topic:       env("KAFKA_TOPIC", "forecast-jobs"),
		group:       env("KAFKA_GROUP", "forecast-workers"),
		deadLetters: env("KAFKA_DLQ_TOPIC", "forecast-jobs.dlq"),
		runURL:      env("BACKEND_RUN_URL", "http://localhost:8081/actuator/forecastjobs"),
		concurrency: concurrency,
		runTimeout:  runTimeout,
		healthAddr:  env("HEALTH_ADDR", ":8090"),
	}, nil
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		os.Exit(healthcheck(env("HEALTH_ADDR", ":8090")))
	}
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("service", "forecast-worker")
	if err := run(logger); err != nil {
		logger.Error("worker stopped", "error", err)
		os.Exit(1)
	}
}

func run(logger *slog.Logger) error {
	cfg, err := loadConfig()
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	if err := ensureTopic(cfg.brokers[0], cfg.deadLetters); err != nil {
		return fmt.Errorf("create dead-letter topic: %w", err)
	}
	deadLetters := &kafka.Writer{
		Addr:         kafka.TCP(cfg.brokers...),
		Topic:        cfg.deadLetters,
		RequiredAcks: kafka.RequireAll,
		Balancer:     &kafka.Hash{},
		BatchTimeout: 10 * time.Millisecond,
	}
	defer deadLetters.Close()

	health := &http.Server{Addr: cfg.healthAddr, Handler: http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}), ReadHeaderTimeout: 5 * time.Second}
	go func() {
		if err := health.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("health server failed", "error", err)
		}
	}()
	defer health.Close()

	runner := &jobs.HTTPRunner{BaseURL: cfg.runURL, Client: &http.Client{Timeout: cfg.runTimeout}}
	logger.Info("worker started", "event", "worker_started", "topic", cfg.topic, "group", cfg.group,
		"concurrency", cfg.concurrency, "run_url", cfg.runURL)

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	errs := make(chan error, cfg.concurrency)
	var wg sync.WaitGroup
	for i := range cfg.concurrency {
		reader := kafka.NewReader(kafka.ReaderConfig{
			Brokers:     cfg.brokers,
			GroupID:     cfg.group,
			Topic:       cfg.topic,
			MinBytes:    1,
			MaxBytes:    1 << 20,
			MaxWait:     time.Second,
			StartOffset: kafka.FirstOffset,
		})
		consumer := &jobs.Consumer{
			Reader:      reader,
			Runner:      runner,
			DeadLetters: deadLetters,
			Logger:      logger.With("consumer", i),
			RunTimeout:  cfg.runTimeout,
			Backoff:     jobs.Backoff{Min: time.Second, Max: 30 * time.Second},
		}
		wg.Add(1)
		go func() {
			defer wg.Done()
			defer reader.Close()
			if err := consumer.Run(ctx); err != nil {
				errs <- err
				cancel()
			}
		}()
	}
	wg.Wait()
	close(errs)
	logger.Info("worker stopping", "event", "worker_stopped")
	return <-errs
}

func ensureTopic(broker, topic string) error {
	conn, err := kafka.Dial("tcp", broker)
	if err != nil {
		return err
	}
	defer conn.Close()
	controller, err := conn.Controller()
	if err != nil {
		return err
	}
	controllerConn, err := kafka.Dial("tcp", net.JoinHostPort(controller.Host, strconv.Itoa(controller.Port)))
	if err != nil {
		return err
	}
	defer controllerConn.Close()
	err = controllerConn.CreateTopics(kafka.TopicConfig{Topic: topic, NumPartitions: 1, ReplicationFactor: 1})
	if errors.Is(err, kafka.TopicAlreadyExists) {
		return nil
	}
	return err
}

func healthcheck(addr string) int {
	host := addr
	if strings.HasPrefix(host, ":") {
		host = "127.0.0.1" + host
	}
	client := &http.Client{Timeout: 3 * time.Second}
	response, err := client.Get("http://" + host + "/healthz")
	if err != nil {
		return 1
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return 1
	}
	return 0
}
