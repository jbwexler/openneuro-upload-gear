FROM mambaorg/micromamba:latest

COPY --chown=$MAMBA_USER:$MAMBA_USER env.yaml /tmp/env.yaml
RUN micromamba create -y -f /tmp/env.yaml && \
	micromamba clean --all --yes

#ENV PATH="/opt/conda/envs/fmriprep/bin:$PATH"
#RUN /opt/conda/envs/fmriprep/bin/npm install -g svgo@^2.8 bids-validator@1.11.0 @openneuro/cli && \
#   rm -r ~/.npm
#COPY requirements.txt /tmp/requirements.txt
#RUN /opt/conda/envs/fmriprep/bin/pip install --no-cache-dir -r /tmp/requirements.txt

#USER root
#ENV FLYWHEEL=/flywheel/v0
#RUN mkdir -p ${FLYWHEEL}
#COPY run.py ${FLYWHEEL}/run.py

#ENTRYPOINT ["python3 run.py"]