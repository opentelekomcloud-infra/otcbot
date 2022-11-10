FROM rust:latest AS builder

ENV DEBIAN_FRONTEND=noninteractive
RUN rustup target add x86_64-unknown-linux-musl
RUN apt update && apt install -y musl-tools musl-dev
RUN update-ca-certificates

# Create appuser
ENV USER=otcbot
ENV UID=10001

RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    "${USER}"

WORKDIR /otcbot

# copy over your manifests
COPY ./Cargo.toml ./Cargo.toml
COPY ./src ./src

RUN cargo build --target x86_64-unknown-linux-musl --release -v

##############
## Final image
##############
FROM scratch as otcbot

# Import from builder.
COPY --from=builder /etc/passwd /etc/passwd
COPY --from=builder /etc/group /etc/group
# COPY ./config.yaml /otcbot/config.yaml

WORKDIR /otcbot

# Copy our build
COPY --from=builder /otcbot/target/x86_64-unknown-linux-musl/release/otcbot ./

# Use an unprivileged user.
USER otcbot:otcbot

# RUN ls -al /otcbot

ENV PATH=/otcbot
CMD ["/otcbot/otcbot"]
