from flask import Flask, render_template
from jira import JIRA

app = Flask(__name__)

# JIRA 配置
JIRA_SERVER = 'http://jira.intchains.in:9000'
JIRA_AUTH = ('xiafeng.luo', 'Luoxiafeng1990@@')

# 连接到 JIRA
jira = JIRA(server=JIRA_SERVER, basic_auth=JIRA_AUTH)

# 获取所有项目
projects = jira.projects()

# 获取 JIRA 面板（示例的 JQL 查询）
jql = "project = 'RDC: Wangshu SDK'"
issues = jira.search_issues(jql, fields="summary, priority, status, creator, created, customfield_11200", maxResults=-1)

@app.route('/')
def home():
    return render_template('index.html', projects=projects, issues=issues)

@app.route('/bsp')
def bsp_page():
    # 示例代码，显示 BSP 相关内容
    return render_template('bsp.html', projects=projects)

@app.route('/sdp')
def sdp_page():
    # 示例代码，显示 SDP 相关内容
    return render_template('sdp.html', projects=projects)

@app.route('/all')
def all_page():
    # 示例代码，显示 All 相关内容
    return render_template('all.html', projects=projects)

if __name__ == '__main__':
    app.run(debug=True)
