FROM fluent/fluentd:v1.17-1

USER root

# Install necessary packages for building Ruby gems
RUN apk add --no-cache --virtual .build-deps \
      build-base \
      ruby-dev \
      libc-dev \
      linux-headers \
      libffi-dev \
      && gem install fluent-plugin-kafka fluent-plugin-parser \
      && apk del .build-deps

# Copy configuration file
COPY fluent.conf /fluentd/etc/
