FROM golang:1.26.2-alpine AS builder

WORKDIR /src

RUN apk add --no-cache ca-certificates git

COPY go.mod go.sum ./
RUN go mod download && go mod verify

COPY . .

ARG TARGETOS=linux
ARG TARGETARCH=amd64
ARG SKAFFOLD_GO_GCFLAGS
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build \
      -ldflags="-s -w" \
      -gcflags="${SKAFFOLD_GO_GCFLAGS}" \
      -trimpath \
      -o /out/shippingservice .

FROM gcr.io/distroless/static:nonroot

COPY --from=builder /out/shippingservice /shippingservice
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

ENV APP_PORT=50051
ENV GOTRACEBACK=single

USER nonroot:nonroot
EXPOSE 50051
ENTRYPOINT ["/shippingservice"]
