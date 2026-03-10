import os
import re
import yaml
import requests
from datetime import datetime

# 从 GitHub Actions 环境变量获取 TOKEN 以提高 API 速率限制
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
headers = {
    'Accept': 'application/vnd.github.v3+json',
    'Authorization': f'Bearer {GITHUB_TOKEN}' if GITHUB_TOKEN else ''
}

def parse_pr_url(url):
    """解析 PR 链接，提取 owner, repo 和 pr_number"""
    match = re.match(r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)', url.strip())
    if match:
        return match.groups()
    return None, None, None

def main():
    # 1. 读取配置文件
    with open('config.yml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    pr_urls = config.get('prs',[])
    
    # 2. 准备目录与内容
    today_str = datetime.now().strftime('%Y-%m-%d')
    digest_dir = f'digests/{today_str}'
    os.makedirs(digest_dir, exist_ok=True)
    
    md_content = f"# 📡 PR 追踪日报 ({today_str})\n\n"
    md_content += f"> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，共追踪 {len(pr_urls)} 个 PR。\n\n"
    
    # 3. 遍历请求信息
    for url in pr_urls:
        owner, repo, pr_number = parse_pr_url(url)
        if not owner:
            md_content += f"## ❌ 无效的 PR 链接\n**URL:** {url}\n\n"
            continue
            
        # 请求 PR 基础信息
        pr_api_url = f'https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}'
        r = requests.get(pr_api_url, headers=headers)
        
        if r.status_code != 200:
            md_content += f"## ⚠️ 获取失败\n**URL:** {url} (可能不存在或无权限)\n\n"
            continue
            
        pr_info = r.json()
        title = pr_info.get('title')
        state = pr_info.get('state')
        merged = pr_info.get('merged', False)
        author = pr_info.get('user', {}).get('login', 'Unknown')
        additions = pr_info.get('additions', 0)
        deletions = pr_info.get('deletions', 0)
        commit_count = pr_info.get('commits', 0)
        
        # 状态判断 (与 GitHub 官方颜色映射一致)
        if merged:
            status_emoji, status_text = "🟣", "已合并 (Merged)"
        elif state == 'closed':
            status_emoji, status_text = "🔴", "已关闭 (Closed)"
        else:
            status_emoji, status_text = "🟢", "开启中 (Open)"
            
        md_content += f"## {status_emoji} [{owner}/{repo}#{pr_number}] {title}\n\n"
        md_content += f"- **链接:** [{url}]({url})\n"
        md_content += f"- **状态:** **{status_text}**\n"
        md_content += f"- **作者:** @{author}\n"
        md_content += f"- **代码变更:** +{additions} / -{deletions} ({commit_count} commits)\n"
        
        # 请求最新 Commit 信息
        head_sha = pr_info.get('head', {}).get('sha')
        if head_sha:
            commit_url = f'https://api.github.com/repos/{owner}/{repo}/commits/{head_sha}'
            c_req = requests.get(commit_url, headers=headers)
            if c_req.status_code == 200:
                commit_data = c_req.json()
                commit_msg = commit_data['commit']['message'].split('\n')[0] # 截取第一行
                commit_date = commit_data['commit']['author']['date']
                
                # 格式化时间
                date_obj = datetime.strptime(commit_date, "%Y-%m-%dT%H:%M:%SZ")
                formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
                
                md_content += f"- **最新 Commit:** `{head_sha[:7]}` - {commit_msg} _(于 {formatted_date})_\n"
        
        md_content += "\n---\n\n"
        
    # 4. 写入 Markdown 文件
    file_path = f'{digest_dir}/pr-report.md'
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
        
    print(f"✅ 报告已生成: {file_path}")

    # 5. 向 GitHub Actions 传递环境变量参数，方便后续建 Issue
    env_file = os.getenv('GITHUB_OUTPUT')
    if env_file:
        with open(env_file, 'a', encoding='utf-8') as f:
            f.write(f"report_path={file_path}\n")
            f.write(f"date={today_str}\n")

if __name__ == "__main__":
    main()
