FROM golang:1.25 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/forecast-worker ./cmd/forecast-worker

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/forecast-worker /forecast-worker
USER nonroot
EXPOSE 8090
ENTRYPOINT ["/forecast-worker"]
