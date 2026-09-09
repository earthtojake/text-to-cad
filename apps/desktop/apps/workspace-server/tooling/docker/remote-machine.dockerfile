FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install --yes --no-install-recommends \
    ca-certificates \
    curl \
    git \
    openssh-server \
    procps \
    sudo \
    tmux \
  && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash devuser \
  && echo 'devuser:devpass' | chpasswd \
  && usermod --append --groups sudo devuser \
  && printf '%s\n' 'devuser ALL=(ALL:ALL) NOPASSWD: ALL' > /etc/sudoers.d/devuser \
  && chmod 0440 /etc/sudoers.d/devuser \
  && visudo --check --file=/etc/sudoers.d/devuser

RUN install -d -m 0755 /run/sshd \
  && ssh-keygen -A \
  && printf '%s\n' \
    'PasswordAuthentication yes' \
    'KbdInteractiveAuthentication no' \
    'PermitRootLogin no' \
    'AllowTcpForwarding yes' \
    'AllowStreamLocalForwarding yes' \
    'ClientAliveInterval 60' \
    'ClientAliveCountMax 10' \
    'MaxSessions 100' \
    'MaxStartups 100:30:200' \
    'X11Forwarding no' \
    > /etc/ssh/sshd_config.d/00-emdash-workspace-remote.conf

USER devuser
WORKDIR /home/devuser

RUN git config --global user.email 'devuser@emdash-dev' \
  && git config --global user.name 'Emdash Dev' \
  && git config --global init.defaultBranch main \
  && git config --global safe.directory '*'

USER root

COPY --chmod=755 entrypoint.sh /entrypoint.sh

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]
