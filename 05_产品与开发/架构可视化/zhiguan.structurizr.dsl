workspace "止观AI" "脑电闭环训练系统 — L1 系统上下文（现状，证据见 architecture-model.json）" {

    model {
        fashi = person "宗国法师" "唯一决策人：驾驶实验、放行提交、裁定候裁项"
        subject = person "修行者/受试者" "佩戴头环完成闭环训练"

        zhiguan = softwareSystem "止观AI" "以 FastAPI 控制台为统一入口，编排脑电采集、实时闭环神经反馈与 WebXR 视觉场景" {
            console = container "实践驾驶舱" "统一入口：监测采集、闭环控制、SSE 推流、会话质检与档案注册" "FastAPI :8777"
            board = container "可视化任务看板" "窗口活跃度、任务进度、维那积压、系统资源；对 AI 窗口只读开放 MCP" "FastAPI 127.0.0.1:8848"
            loop = container "闭环实验链" "采集频段 → 阈值决策 → 调节等时节拍频率与音量" "Python"
            vr = container "VR 视觉场景" "曼荼罗 / 反馈场景，承接节拍视觉反馈" "WebXR + Three.js"
        }

        muse = softwareSystem "Muse 头环" "消费级脑电硬件，BLE 出流" "External" {
            tags "External"
        }
        neuradock = softwareSystem "NeuraDock 工作站" "七通道头环 250Hz，TCP :9600" "External" {
            tags "External"
        }
        qianwen = softwareSystem "千问 LLM API" "模型探活与生成，属出网三级制管辖" "External" {
            tags "External"
        }
        feishu = softwareSystem "飞书" "维那看板快照来源" "External" {
            tags "External"
        }
        qoder = softwareSystem "Qoder AI 窗口群" "多窗协作：会话与任务元数据落在 ~/.qoder-cn" "External" {
            tags "External"
        }
        zeneeg = softwareSystem "Zen-EEG 登记册" "跨盘 session_registry.csv 会话档案" "External" {
            tags "External"
        }

        fashi -> console "驾驶实验、查看监测" "HTTPS"
        fashi -> board "查看窗口与任务进度" "HTTP"
        subject -> muse "佩戴采集"
        subject -> vr "沉浸训练"

        muse -> loop "BLE 脑电原始流" "BLE"
        neuradock -> console "头环数据扇入" "TCP"
        loop -> vr "节拍频率/音量 → 视觉反馈" "in-process"
        console -> loop "启动与控制闭环" "in-process"
        console -> zeneeg "读写会话档案" "file/CSV"
        board -> qianwen "模型探活" "HTTPS"
        board -> feishu "拉取维那快照" "HTTPS"
        qoder -> board "tools/call：board_overview、board_windows" "MCP over HTTP"
    }

    views {
        systemContext zhiguan "L1-Context" "止观AI 与外部世界的边界：硬件、AI 窗口群、出网服务" {
            include *
            autolayout tb
        }

        container zhiguan "L2-Containers" "止观AI 内部四个可部署单元" {
            include *
            autolayout tb
        }

        styles {
            element "Person" {
                shape person
                background #ff9800
                color #ffffff
            }
            element "External" {
                background #b0bec5
                color #263238
            }
            element "Software System" {
                background #1976d2
                color #ffffff
            }
            element "Container" {
                background #42a5f5
                color #ffffff
            }
        }
    }
}
