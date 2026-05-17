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
      -o /out/productcatalogservice .

FROM gcr.io/distroless/static:nonroot

WORKDIR /src

COPY --from=builder /out/productcatalogservice /src/server
COPY --from=builder /src/products.json /src/products.json
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

ENV GOTRACEBACK=single

USER nonroot:nonroot
EXPOSE 3550
ENTRYPOINT ["/src/server"]
