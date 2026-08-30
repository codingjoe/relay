FROM node:26-slim AS frontend
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    npm install -g pnpm && pnpm ci --frozen-lockfile
COPY ./ /app
RUN mkdir -p root/static/css && pnpm run build

FROM ghcr.io/astral-sh/uv:0.12.7-trixie-slim AS build
LABEL title="SMTP Server"
LABEL license="BSD-2-Clause"
LABEL url="https://github.com/codingjoe/the-box"

# Install dependencies
RUN --mount=type=bind,source=./Aptfile,target=/tmp/Aptfile \
    cd /tmp && apt-get update && cat Aptfile | xargs apt-get download \
    && mkdir -p /dpkg && \
    for deb in *.deb; do dpkg --extract $deb /dpkg || exit 10; done

# UV
ARG UV_NO_DEV
ENV UV_NO_DEV=${UV_NO_DEV:-1}
ENV UV_PYTHON_PREFERENCE=only-managed
ENV UV_PYTHON_INSTALL_DIR=/opt/python
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1

# Install Python and dependencies
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=./uv.lock,target=uv.lock \
    --mount=type=bind,source=./pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-editable

FROM gcr.io/distroless/cc:debug AS development

# Copy binary dependencies
COPY --from=build /dpkg /

# Copy Python dependencies
COPY --from=build --chown=root:root /opt/python /opt/python
COPY --from=build --chown=root:root /opt/venv /opt/venv

# Create the virtual environment
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
ENV PORT=8000

WORKDIR /app

ENTRYPOINT ["/opt/venv/bin/python"]

FROM build AS compile

RUN apt-get install -y gettext

COPY ./ /app

# Compile message files
RUN /opt/venv/bin/python -m manage compilemessages

# Copy compiled CSS from the frontend build stage
COPY --from=frontend /app/root/static/css/app.css /app/root/static/css/app.css

# Collect static files
RUN /opt/venv/bin/python -m manage collectstatic --no-input

FROM development AS production

COPY ./ /app

COPY --from=compile /app/root/locale /app/root/locale
COPY --from=compile /app/staticfiles /app/staticfiles

WORKDIR /app
ENTRYPOINT ["/opt/venv/bin/python"]
