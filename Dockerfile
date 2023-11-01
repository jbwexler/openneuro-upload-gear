FROM mambaorg/micromamba:1.5.1
USER root

COPY --chown=$MAMBA_USER:$MAMBA_USER env.yaml /tmp/env.yaml
RUN micromamba create -y -f /tmp/env.yaml && \
	micromamba clean --all --yes

ENV PATH="/opt/conda/envs/openneuro-upload/bin:$PATH"
RUN /opt/conda/envs/openneuro-upload/bin/npm install -g @openneuro/cli && \
	rm -r ~/.npm
COPY requirements.txt /tmp/requirements.txt
RUN /opt/conda/envs/openneuro-upload/bin/pip install --no-cache-dir -r /tmp/requirements.txt

ENV FLYWHEEL=/flywheel/v0
RUN mkdir -p ${FLYWHEEL}
COPY run.py ${FLYWHEEL}/run.py
#COPY gitattributes.txt /flywheel/v0/work/
COPY gitattributes.txt ${FLYWHEEL}/gitattributes.txt
WORKDIR ${FLYWHEEL}

ENTRYPOINT ["/flywheel/v0/run.py"]
