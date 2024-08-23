FROM python:3.11

WORKDIR /

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
RUN apt-get -qq update && apt-get -qq install -y git
RUN python -m venv venv
ENV PATH="/venv/bin:$PATH"

# Configure pip to use the specified Huawei mirror and set trusted hosts
RUN pip config set global.index-url http://mirrors.tools.huawei.com/pypi/simple \
    && pip config set global.trusted-host "mirrors.tools.huawei.com rnd-gitlab-eu.huawei.com pypi.org files.pythonhosted.org"