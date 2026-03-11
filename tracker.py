import os
import re
import yaml
import requests
from datetime import datetime

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
headers = {
    'Accept': 'application/vnd.github.v3+json',
    'Authorization': f'Bearer {GITHUB_TOKEN}' if GITHUB_TOKEN else ''
}

def parse_pr_url(url):
    match = re.match(r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)', url.strip())
    if match:
        return match.groups()
    return None, None, None

def main():
    # 1. 读取配置文件
    with open('config.yml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    pr_urls = config.get('prs', []) or []
    active_prs =[] # 用于保存还需要继续追踪的 PR（Open 状态）
    has_changes = False # 记录配置是否需要更新
    
    # 2. 准备目录与内容
    today_str = datetime.now().strftime('%Y-%m-%d')
    digest_dir = f'digests/{today_str}'
    os.makedirs(digest_dir, exist_ok=True)
    
    md_content = f"# 📡 PR 追踪日报 ({today_str})\n\n"
    md_content += f"> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，本次共查询 {len(pr_urls)} 个 PR。\n\n"
    
    # 3. 遍历请求信息
    for url in pr_urls:
        owner, repo, pr_number = parse_pr_url(url)
        if not owner:
            md_content += f"## ❌ 无效的 PR 链接\n**URL:** {url}\n\n"
            has_changes = True # 无效链接也将其剔除
            continue
            
        pr_api_url = f'https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}'
        r = requests.get(pr_api_url, headers=headers)
        
        if r.status_code != 200:
            md_content += f"## ⚠️ 获取失败\n**URL:** {url} (可能不存在或无权限)\n\n"
            # 获取失败暂不剔除，防止是网络偶发故障
            active_prs.append(url)
            continue
            
        pr_info = r.json()
        title = pr_info.get('title')
        state = pr_info.get('state')
        merged = pr_info.get('merged', False)
        author = pr_info.get('user', {}).get('login', 'Unknown')
        additions = pr_info.get('additions', 0)
        deletions = pr_info.get('deletions', 0)
        commit_count = pr_info.get('commits', 0)
        
        # 状态判断与分类
        if merged:
            status_emoji, status_text = "🟣", "已合并 (Merged)"
            has_changes = True # 已合并，不再追踪
        elif state == 'closed':
            status_emoji, status_text = "🔴", "已关闭 (Closed)"
            has_changes = True # 已关闭，不再追踪
        else:
            status_emoji, status_text = "🟢", "开启中 (Open)"
            active_prs.append(url) # 开启中，保留到 config 中以便明日追踪
            
        md_content += f"## {status_emoji}[{owner}/{repo}#{pr_number}] {title}\n\n"
        md_content += f"- **链接:** [{url}]({url})\n"
        md_content += f"- **状态:** **{status_text}**\n"
        md_content += f"- **作者:** @{author}\n"
        md_content += f"- **代码变更:** +{additions} / -{deletions} ({commit_count} commits)\n"
        
        head_sha = pr_info.get('head', {}).get('sha')
        if head_sha:
            commit_url = f'https://api.github.com/repos/{owner}/{repo}/commits/{head_sha}'
            c_req = requests.get(commit_url, headers=headers)
            if c_req.status_code == 200:
                commit_data = c_req.json()
                commit_msg = commit_data['commit']['message'].split('\n')[0]
                commit_date = commit_data['commit']['author']['date']
                
                date_obj = datetime.strptime(commit_date, "%Y-%m-%dT%H:%M:%SZ")
                formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
                
                md_content += f"- **最新 Commit:** `{head_sha[:7]}` - {commit_msg} _(于 {formatted_date})_\n"
        
        md_content += "\n---\n\n"
        
    # 4. 写入 Markdown 文件
    file_path = f'{digest_dir}/pr-report.md'
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"✅ 报告已生成: {file_path}")

    # 5. 【新增逻辑】如果 PR 状态有变更（被剔除），则更新 config.yml
    if has_changes:
        config['prs'] = active_prs
        with open('config.yml', 'w', encoding='utf-8') as f:
            # allow_unicode=True 保证中文字符不被转码，sort_keys=False 保持键的顺序
            yaml.dump(config, f, allow_unicode=True, sort_keys=False)
        print(f"♻️ config.yml 已更新，当前剩余 {len(active_prs)} 个 PR 待追踪。")

    # 6. 向 GitHub Actions 传递参数
    env_file = os.getenv('GITHUB_OUTPUT')
    if env_file:
        with open(env_file, 'a', encoding='utf-8') as f:
            f.write(f"report_path={file_path}\n")
            f.write(f"date={today_str}\n")

if __name__ == "__main__":
    main()
