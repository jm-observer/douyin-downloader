# Docker 使用说明

## 构建镜像

```bash
# 构建Docker镜像
docker build -t douyin-downloader .
```

## 运行容器

### 方式一：交互式运行（推荐）

```bash
# 运行容器并进入交互模式
docker run -it --rm \
  -v $(pwd):/app \
  -v $(pwd)/Downloaded:/app/Downloaded \
  douyin-downloader bash
```

### 方式二：直接运行命令

```bash
# 运行V1.0版本（需要先配置config.yml）
docker run --rm \
  -v $(pwd):/app \
  -v $(pwd)/Downloaded:/app/Downloaded \
  douyin-downloader python DouYinCommand.py

# 运行V2.0版本
docker run --rm \
  -v $(pwd):/app \
  -v $(pwd)/Downloaded:/app/Downloaded \
  douyin-downloader python downloader.py --help
```

## 使用示例

### 1. 进入容器进行配置

```bash
# 启动交互式容器
docker run -it --rm \
  -v $(pwd):/app \
  -v $(pwd)/Downloaded:/app/Downloaded \
  douyin-downloader bash

# 在容器内配置Cookie
python cookie_extractor.py

# 或手动配置
python get_cookies_manual.py
```

### 2. 下载单个视频

```bash
# 使用V1.0版本
docker run --rm \
  -v $(pwd):/app \
  -v $(pwd)/Downloaded:/app/Downloaded \
  douyin-downloader python DouYinCommand.py

# 使用V2.0版本
docker run --rm \
  -v $(pwd):/app \
  -v $(pwd)/Downloaded:/app/Downloaded \
  douyin-downloader python downloader.py -u "https://v.douyin.com/xxxxx/"
```

### 3. 下载用户主页

```bash
# 使用V2.0版本（推荐）
docker run --rm \
  -v $(pwd):/app \
  -v $(pwd)/Downloaded:/app/Downloaded \
  douyin-downloader python downloader.py -u "https://www.douyin.com/user/xxxxx"
```

## 注意事项

1. **配置文件**：确保在宿主机上创建了`config.yml`或`config_simple.yml`配置文件
2. **Cookie配置**：首次使用需要配置Cookie，可以在容器内运行`python cookie_extractor.py`
3. **下载目录**：下载的文件会保存到宿主机的`./Downloaded`目录
4. **网络访问**：容器需要网络访问来下载视频，确保Docker有网络权限

## 常用命令

```bash
# 查看镜像
docker images | grep douyin-downloader

# 删除镜像
docker rmi douyin-downloader

# 查看容器日志
docker logs <container_id>

# 进入运行中的容器
docker exec -it <container_id> bash
```
