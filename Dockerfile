ARG ROSETTA_IMAGE=rosettacommons/rosetta:serial

FROM --platform=linux/amd64 ${ROSETTA_IMAGE} AS rosetta

FROM --platform=linux/amd64 continuumio/miniconda3:latest

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      curl \
      file \
      git \
      perl \
      procps \
      tcsh \
      unzip \
      libgl1 \
      libxrender1 \
      libxext6 \
      libsm6 \
      libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN conda config --set always_yes true \
 && conda config --set channel_priority strict \
 && conda install -n base -c conda-forge mamba \
 && mamba create -n prosettac -c conda-forge \
        python=3.11 \
        numpy \
        scikit-learn \
        rdkit \
        openbabel \
        pymol-open-source \
 && mamba create -n py27 -c conda-forge python=2.7 \
 && conda clean -afy \
 && ln -sf /opt/conda/envs/py27/bin/python2.7 /usr/local/bin/python2.7 \
 && ln -sf /opt/conda/envs/prosettac/bin/obabel /opt/conda/envs/prosettac/bin/babel

# Sparse-checkout only the Python helper subtrees PRosettaC needs from the
# public RosettaCommons repos at pinned commit SHAs. The compiled binary and
# database come from the upstream rosettacommons/rosetta image below.
# ARG names must NOT start with "ROSETTA_" — Docker exports them into RUN
# env, and Apple Rosetta 2 (macOS amd64 emulator) aborts any process that
# sets an unrecognized ROSETTA_* env var.
ARG SCRIPTS_REPO_SHA=068bd85322153b1ddc5a354f8cf0633a5631e9fa
ARG TOOLS_REPO_SHA=bad7cd848616906e772c10274144ffe3a09fa98a

RUN mkdir -p /opt/rosetta/main/source/scripts/python /opt/rosetta/tools \
 && git clone --filter=blob:none --no-checkout \
        https://github.com/RosettaCommons/rosetta.git /tmp/r \
 && git -C /tmp/r sparse-checkout init --cone \
 && git -C /tmp/r sparse-checkout set source/scripts/python/public \
 && git -C /tmp/r checkout "${SCRIPTS_REPO_SHA}" \
 && mv /tmp/r/source/scripts/python/public /opt/rosetta/main/source/scripts/python/public \
 && rm -rf /tmp/r \
 && git clone --filter=blob:none --no-checkout \
        https://github.com/RosettaCommons/tools.git /tmp/t \
 && git -C /tmp/t sparse-checkout init --cone \
 && git -C /tmp/t sparse-checkout set protein_tools \
 && git -C /tmp/t checkout "${TOOLS_REPO_SHA}" \
 && mv /tmp/t/protein_tools /opt/rosetta/tools/protein_tools \
 && rm -rf /tmp/t

# Compiled binary + database from the upstream image. Place the bin tree at
# the exact path PRosettaC hardcodes so the RPATH ($ORIGIN) still finds its
# sibling shared libs. Keep this COPY last because the resulting amd64 layer
# is large enough to destabilize subsequent RUN steps under emulation.
COPY --from=rosetta /usr/local/bin /opt/rosetta/main/source/bin
COPY --from=rosetta /usr/local/lib/python3.8/dist-packages/pyrosetta/database /opt/rosetta/main/database

ENV PROSETTAC_HOME=/opt/prosettac \
    ROSETTA3_HOME=/opt/rosetta \
    ROSETTA3_DB=/opt/rosetta/main/database \
    PATCHDOCK=/opt/patchdock \
    OB=/opt/conda/envs/prosettac/bin \
    SCRIPTS_FOL=/opt/prosettac/ \
    CONDA_ENV=prosettac \
    PATH=/opt/conda/envs/prosettac/bin:/opt/conda/bin:$PATH

WORKDIR /opt/prosettac
COPY . /opt/prosettac

WORKDIR /work
ENTRYPOINT ["/opt/prosettac/docker/entrypoint.sh"]
CMD ["--help"]
