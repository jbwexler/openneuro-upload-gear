FROM mambaorg/micromamba:2.5.0
USER root

COPY env.yaml /tmp/env.yaml
RUN micromamba create -y -f /tmp/env.yaml && \
	micromamba clean --all --yes

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
                    bc \
                    ca-certificates \
                    curl \
                    git \
                    gnupg \
                    lsb-release \
                    netbase \
                    xvfb && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*


ENV FLYWHEEL=/flywheel/v0
COPY package.json ${FLYWHEEL}/package.json
WORKDIR ${FLYWHEEL}

COPY --from=denoland/deno:bin-2.7.13 /deno /usr/local/bin/deno
ENV PATH="/root/.deno/bin:$PATH"
ENV PATH="/opt/conda/envs/openneuro-upload/bin:$PATH"
RUN deno install -A --global jsr:@openneuro/cli -n openneuro
RUN deno install -A --global jsr:@bids/validator -n bids-validator

RUN curl https://raw.githubusercontent.com/OpenNeuroOrg/openneuro/refs/heads/master/bin/git-annex-remote-openneuro -o /usr/local/bin/git-annex-remote-openneuro && \
    chmod +x /usr/local/bin/git-annex-remote-openneuro

COPY requirements.txt /tmp/requirements.txt
RUN /opt/conda/envs/openneuro-upload/bin/pip install --no-cache-dir -r /tmp/requirements.txt

RUN mkdir -p ${FLYWHEEL}
COPY run.py ${FLYWHEEL}/run.py
COPY gitconfig.txt /root/.gitconfig
COPY bids-validator-config_ddjson-err.json ${FLYWHEEL}/bids-validator-config_ddjson-err.json
COPY bids-validator-config_ddjson-warn.json ${FLYWHEEL}/bids-validator-config_ddjson-warn.json
WORKDIR ${FLYWHEEL}

ENTRYPOINT ["/flywheel/v0/run.py"]
