FROM mcr.microsoft.com/dotnet/sdk:10.0.100-noble AS builder

ARG RUNTIME_ID=linux-x64
WORKDIR /src

COPY src/cartservice.csproj ./src/
RUN dotnet restore ./src/cartservice.csproj -r ${RUNTIME_ID}

COPY src ./src
RUN dotnet publish ./src/cartservice.csproj \
    -c Release \
    -r ${RUNTIME_ID} \
    --self-contained true \
    -p:PublishSingleFile=true \
    -p:PublishTrimmed=true \
    -p:TrimMode=full \
    --no-restore \
    -o /out/cartservice

FROM mcr.microsoft.com/dotnet/runtime-deps:10.0.0-noble-chiseled

WORKDIR /app
COPY --from=builder /out/cartservice ./

ENV DOTNET_EnableDiagnostics=0
ENV ASPNETCORE_HTTP_PORTS=7070

USER 1000:1000
EXPOSE 7070
ENTRYPOINT ["/app/cartservice"]
