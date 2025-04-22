# .ide/Dockerfile
FROM python:3.8

# 安装 code-server 和扩展（使用 id 安装 python 扩展，使用 vsix 安装包安装 pylance 扩展）
RUN curl -fsSL https://code-server.dev/install.sh | sh \
  && code-server --install-extension ms-python.python \
  && code-server --install-extension ms-ceintl.vscode-language-pack-zh-hans \
  && echo done

# 安装 ssh 服务，用于支持 VSCode 客户端通过 Remote-SSH 访问开发环境
RUN apt-get update && apt-get install -y wget unzip openssh-server

# 指定字符集支持命令行输入中文（根据需要选择字符集）
ENV LANG C.UTF-8
ENV LANGUAGE C.UTF-8
