FROM mambaorg/micromamba:1.5.1
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
ENV PATH="/opt/conda/envs/openneuro-upload/bin:$PATH"
RUN /opt/conda/envs/openneuro-upload/bin/npm install && \
	rm -r ~/.npm
ENV	PATH="${FLYWHEEL}/node_modules/.bin:$PATH"
COPY requirements.txt /tmp/requirements.txt
RUN /opt/conda/envs/openneuro-upload/bin/pip install --no-cache-dir -r /tmp/requirements.txt

RUN mkdir -p ${FLYWHEEL}
COPY run.py ${FLYWHEEL}/run.py
COPY test_bids_ds ${FLYWHEEL}/test_bids_ds
COPY gitconfig.txt /root/.gitconfig
COPY bids-validator-config_ddjson-err.json ${FLYWHEEL}/bids-validator-config_ddjson-err.json
COPY bids-validator-config_ddjson-warn.json ${FLYWHEEL}/bids-validator-config_ddjson-warn.json
WORKDIR ${FLYWHEEL}

ENTRYPOINT ["/flywheel/v0/run.py"]
