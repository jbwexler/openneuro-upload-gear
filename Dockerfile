FROM mambaorg/micromamba:1.5.1

COPY --chown=$MAMBA_USER:$MAMBA_USER env.yaml /tmp/env.yaml
RUN micromamba create -y -f /tmp/env.yaml && \
	micromamba clean --all --yes

ENV PATH="/opt/conda/envs/openneuro-upload/bin:$PATH"
RUN /opt/conda/envs/openneuro-upload/bin/npm install -g @openneuro/cli && \
    rm -r ~/.npm
COPY requirements.txt /tmp/requirements.txt
RUN /opt/conda/envs/openneuro-upload/bin/pip install --no-cache-dir -r /tmp/requirements.txt

USER root
ENV FLYWHEEL=/flywheel/v0
RUN mkdir -p ${FLYWHEEL}
COPY run.py ${FLYWHEEL}/run.py
#USER $MAMBA_USER
WORKDIR ${FLYWHEEL}
