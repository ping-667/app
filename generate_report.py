"""Generate compact A4 report for hands-on development assessment."""
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os

doc = Document()

# ---- Page setup ----
for section in doc.sections:
    section.page_width  = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin    = Cm(1.2)
    section.bottom_margin = Cm(1.0)
    section.left_margin   = Cm(1.2)
    section.right_margin  = Cm(1.2)

# ---- Default style ----
style = doc.styles['Normal']
style.font.name = 'Arial'
style.font.size = Pt(9)
style.paragraph_format.space_before = Pt(0)
style.paragraph_format.space_after  = Pt(1)
style.paragraph_format.line_spacing = 1.05

# Set CJK font
rPr = style.element.find(qn('w:rPr'))
if rPr is None:
    rPr = OxmlElement('w:rPr')
    style.element.append(rPr)
rFonts = rPr.find(qn('w:rFonts'))
if rFonts is None:
    rFonts = OxmlElement('w:rFonts')
    rPr.append(rFonts)
rFonts.set(qn('w:eastAsia'), '微软雅黑')

# ---- Helper functions ----
def add_title(text, size=18):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0x1a, 0x3c, 0x6e)
    return p

def add_subtitle(text, size=9):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    return p

def add_heading_styled(text, level=1):
    h = doc.add_heading(text, level=level)
    h.paragraph_format.space_before = Pt(6 if level == 1 else 3)
    h.paragraph_format.space_after  = Pt(2)
    for run in h.runs:
        run.font.name = 'Arial'
        run.font.color.rgb = RGBColor(0x1a, 0x3c, 0x6e)
        if level == 1:
            run.font.size = Pt(11)
        else:
            run.font.size = Pt(9.5)
    return h

def add_para(text, bold=False, indent=0, size=9):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.space_before = Pt(0)
    if indent:
        p.paragraph_format.left_indent = Cm(indent)
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = 'Arial'
    return p

def add_bullet(text, size=8.5):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.first_line_indent = Cm(-0.3)
    run = p.add_run('• ' + text)
    run.font.size = Pt(size)
    run.font.name = 'Arial'
    return p

def fmt_cell(cell, text, bold=False, size=8, align='left', color=None):
    """Format a table cell."""
    cell.text = ''
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(1)
    p.paragraph_format.line_spacing = 1.0
    if align == 'center':
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = 'Arial'
    if color:
        run.font.color.rgb = color

def set_cell_shading(cell, color):
    shading = OxmlElement('w:shd')
    shading.set(qn('w:fill'), color)
    shading.set(qn('w:val'), 'clear')
    cell._tc.get_or_add_tcPr().append(shading)

def add_table(headers, rows, col_widths=None):
    """Create a compact table."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    # Set borders
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement('w:tblPr')
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{edge}')
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), '4')
        el.set(qn('w:color'), '999999')
        borders.append(el)
    tblPr.append(borders)

    # Header row
    for i, h in enumerate(headers):
        c = table.rows[0].cells[i]
        fmt_cell(c, h, bold=True, size=8, color=RGBColor(0xff, 0xff, 0xff))
        set_cell_shading(c, '1a3c6e')

    # Data rows
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            c = table.rows[ri + 1].cells[ci]
            fmt_cell(c, str(val), size=7.5)
            if ri % 2 == 1:
                set_cell_shading(c, 'f0f3f7')

    # Column widths
    if col_widths:
        for ri in range(len(rows) + 1):
            for ci, w in enumerate(col_widths):
                table.rows[ri].cells[ci].width = Cm(w)

    doc.add_paragraph()  # spacer
    return table

# ---- Thin line separator ----
def add_line():
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(1)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '4')
    bottom.set(qn('w:color'), 'CCCCCC')
    bottom.set(qn('w:space'), '1')
    pBdr.append(bottom)
    pPr.append(pBdr)

# ============================================================
# PAGE 1
# ============================================================

add_title('QQ群消息监控系统', size=18)
add_subtitle('实操开发考核报告  |  Python + Flask + NapCatQQ  |  MIT License')

add_line()

# ---- 1. 项目概述 ----
add_heading_styled('1  项目概述', level=1)
add_para(
    '本系统是一个面向学生群体的QQ群消息实时监控平台。通过NapCatQQ对接OneBot 11标准协议实时采集群聊消息，'
    '结合关键词匹配引擎与桌面通知机制，帮助用户在第一时间获取作业布置、考试通知等重要信息。'
    '系统采用Flask Web框架 + SQLite数据库 + bcrypt安全认证，支持多用户隔离、Chart.js数据可视化和Docker一键部署。'
    '代码总规模约2200行（Python 1250行 + 前端JS/CSS/HTML 950行），7个核心Python模块 + 2个前端页面。',
    size=8.5
)

# ---- 2. 系统架构 ----
add_heading_styled('2  系统架构（三层设计）', level=1)

# Architecture table
add_table(
    ['层级', '核心组件', '职责说明'],
    [
        ['采集层', 'QQ → NapCatQQ → OneBot WebSocket (:3001)', '实时消息采集（零延迟），完全基于OneBot 11标准协议'],
        ['存储层', 'Monitor调度引擎 → Detector关键词匹配 + SHA256去重 → SQLite (WAL)', '消息调度、关键词精确/正则双模式匹配、60s窗口去重、数据持久化'],
        ['展示层', 'Flask Web (:5000) → 消息记录 / 关键词管理 / Chart.js看板 / plyer通知', 'Web管理面板、数据可视化、桌面弹窗提醒、CSV导出'],
    ],
    col_widths=[2.2, 5.8, 8.5]
)

# ---- 3. 核心技术栈 ----
add_heading_styled('3  核心技术栈', level=1)

add_table(
    ['层次', '技术选型'],
    [
        ['后端框架', 'Python 3.9+  /  Flask  /  WebSocket'],
        ['消息采集', 'NapCatQQ (QQ消息钩子)  /  OneBot 11 标准协议 (WebSocket正向连接)'],
        ['数据存储', 'SQLite (WAL模式+索引优化)  /  bcrypt 密码哈希  /  Session 认证'],
        ['前端展示', '原生 JavaScript  /  Chart.js 4.x  /  暗色监控控制台 CSS 主题  /  plyer 桌面通知'],
        ['部署运维', 'Docker  /  Docker Compose  /  Windows 一键启动脚本  /  frp/Cloudflare Tunnel 公网'],
    ],
    col_widths=[2.2, 14.3]
)

# ---- 4. 核心模块 ----
add_heading_styled('4  核心模块说明', level=1)

add_table(
    ['模块文件', '职责', '关键实现'],
    [
        ['app.py (388行)', 'Flask Web入口，19个API端点',
         '用户认证(注册/登录/登出)、关键词CRUD(增删改查+重置)、消息查询/删除/清空、监控启动/停止/状态、统计接口、CSV导出、login_required装饰器'],
        ['config.py (52行)', '全局配置管理',
         '18个默认教育场景关键词(考试/考核/作业/截止日期/提交/期中/期末/答辩/查重/签到等)、JSON文件持久化、get/set接口、Config类'],
        ['database.py (325行)', 'SQLite数据访问层',
         '3张表(users/messages/user_config)、WAL模式+索引优化、bcrypt认证+旧SHA256自动升级、参数化查询防SQL注入、CSV导出(UTF-8 BOM)'],
        ['detector.py (153行)', '关键词检测核心引擎',
         'OneBot消息处理+OCR文本处理(备选)、精确/正则双模式匹配、SHA256内容哈希60s窗口去重、发送者QQ聊天格式正则解析'],
        ['monitor.py (132行)', '后台监控调度引擎',
         'OneBotClient生命周期管理、消息→检测→入库→通知全流程编排、daemon线程运行、plyer桌面通知'],
        ['onebot_client.py (185行)', 'OneBot 11 WebSocket客户端',
         '正向连接NapCatQQ :3001、指数退避自动重连(2s→60s)、群聊/私聊事件解析、群名过滤、消息队列解耦'],
        ['utils.py (27行)', '工具函数',
         'DPI感知设置(Win32 API)、日志配置(文件+控制台双输出)'],
        ['diag.py (150行)', 'QQ窗口诊断工具',
         '窗口枚举/定位/截图验证，辅助排查采集环境问题'],
        ['前端 (static+templates)', 'Web管理面板UI',
         'app.js(330行): Chart.js可视化+API交互 / style.css(427行): 暗色监控控制台主题 / index.html+login.html(207行): 页面结构'],
    ],
    col_widths=[3.2, 3.4, 9.9]
)

# ---- 5. 数据流 ----
add_heading_styled('5  数据流', level=1)

doc.add_paragraph()
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(2)
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
pPr = p._p.get_or_add_pPr()
pBdr = OxmlElement('w:pBdr')
bottom = OxmlElement('w:bottom')
bottom.set(qn('w:val'), 'single')
bottom.set(qn('w:sz'), '6')
bottom.set(qn('w:color'), '1a3c6e')
bottom.set(qn('w:space'), '4')
pBdr.append(bottom)
pPr.append(pBdr)

flow_text = (
    'QQ群消息  ───  NapCatQQ消息钩子  ───  '
    'OneBot 11 WebSocket\n(ws://127.0.0.1:3001)  ───  '
    'OneBotClient接收  ───  Monitor调度\n'
    '───  Detector关键词匹配 + SHA256去重  ───  '
    'Database写入SQLite\n───  Web Dashboard实时展示 + plyer桌面通知弹窗'
)
run = p.add_run(flow_text)
run.font.size = Pt(8)
run.font.name = 'Arial'
run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

add_line()

# ---- 6. 功能特性 ----
add_heading_styled('6  功能特性清单', level=1)

features = [
    'OneBot WebSocket实时采集  —  对接NapCatQQ，零延迟获取群消息，无需保持QQ窗口可见',
    '双模式关键词匹配  —  精确匹配（子串包含）+ 正则匹配，灵活定义筛选规则',
    'SHA256内容去重  —  60秒滑动窗口内相同消息自动过滤，避免重复告警',
    'WebSocket自动重连  —  指数退避策略（2s→60s max），断线自动恢复，30s心跳日志',
    '桌面即时通知  —  命中关键词时通过plyer弹出Windows原生通知（10s持续显示）',
    'Web管理面板  —  消息记录浏览/筛选/删除、关键词增删改查/重置默认、监控启停控制',
    '多用户系统  —  注册/登录/登出、bcrypt密码哈希、Session认证、数据按user_id物理隔离',
    'Chart.js数据可视化  —  关键词命中排行柱状图 + 活跃发送者Top10分布图',
    'CSV一键导出  —  消息记录导出为CSV文件（UTF-8 BOM编码，存入 %APPDATA%/QQMonitor/exports）',
    'Docker容器化部署  —  Dockerfile + docker-compose.yml，一行命令启动',
    '群名过滤 + 私聊支持  —  支持按群名筛选监听范围，私聊消息自动以"私聊-发送者"命名',
    '关键词下拉框智能合并  —  用户配置关键词与历史命中关键词合并展示，新关键词即时可选',
]
for ft in features:
    add_bullet(ft, size=8)

# ---- 7. 关键技术决策 ----
add_heading_styled('7  关键技术决策', level=1)

decisions = [
    ['协议选型', '选用OneBot 11标准协议而非QQ私有API，保证跨框架兼容性（支持NapCatQQ/LLOneBot）和长期稳定性'],
    ['连接模式', '采用WebSocket正向连接（主动连接NapCatQQ），比反向HTTP上报更简单可靠，断线自动重连，指数退避2s→60s'],
    ['数据库', 'SQLite而非MySQL/PostgreSQL，零配置零运维，WAL模式保障并发读写性能，3个索引优化查询，满足单机场景需求'],
    ['安全认证', 'bcrypt代替SHA256做密码哈希，内置salt和cost factor；兼容旧密码自动升级，无需用户重新设置'],
    ['多用户', '数据按user_id物理隔离，所有SQL查询带user_id条件，支持多用户共用同一实例互不干扰'],
    ['消息去重', 'SHA256(发送者+内容规范化)哈希 + 60s滑动窗口时间衰减，有效避免群聊中同一消息重复告警'],
]
for dec in decisions:
    add_bullet(f'{dec[0]}：{dec[1]}', size=8)

# ---- 8. 项目信息 ----
add_heading_styled('8  项目信息', level=1)

add_table(
    ['项目', '详情'],
    [
        ['开发语言', 'Python 3.9+'],
        ['代码规模', '7个核心Python模块（~1250行）+ 前端（~950行 JS/CSS/HTML）+ 诊断工具（diag.py 150行），总计约2350行'],
        ['代码仓库', 'github.com/ping-667/app'],
        ['开源协议', 'MIT License'],
        ['部署方式', 'Windows 一键启动（启动.bat）/ Docker Compose'],
        ['依赖服务', 'NapCatQQ（QQ消息钩子，需独立安装启动）'],
    ],
    col_widths=[2.5, 14]
)

# ---- Footer ----
doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('— END —')
run.font.size = Pt(8)
run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
run.font.name = 'Arial'

# ---- Save ----
output_path = 'E:/程序/项目开发报告.docx'
doc.save(output_path)
print(f'Report saved to: {output_path}')
