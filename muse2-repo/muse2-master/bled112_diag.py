#!/usr/bin/env python3
"""BLED112 分层诊断（2026-09-09）：逐层打印真实异常，定位"连不上"根因。

层级：L1 串口发现 → L2 BGAPI 后端启动 → L3 扫描头环 → L4 连接
      → L5 特征枚举 → L6 订阅 EEG 通知 → L7 收包计数（15 秒）
只读诊断：不写任何数据文件、不改变系统配置。
用法：python bled112_diag.py [串口]   （不传则自动检测）
"""
import asyncio
import sys
import time
import traceback

import serial.tools.list_ports

BLED112_VID = 0x2458

def L(n, msg):
    print(f"[L{n}] {msg}", flush=True)

def main():
    # 参数：单个参数可为串口（COM3）或头环 MAC（含冒号）；MAC 模式跳过扫描直连
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    port = None
    addr = None
    if arg:
        if ":" in arg:
            addr = arg
        else:
            port = arg
    # L1 串口发现
    if not port:
        cands = [(p.device, getattr(p, "vid", None), getattr(p, "pid", None))
                 for p in serial.tools.list_ports.comports()]
        L(1, f"全部串口: {cands}")
        hit = [d for d, v, _ in cands if v == BLED112_VID]
        if not hit:
            L(1, "❌ 未发现 BLED112（vid=0x2458）。请确认适配器已插入。")
            return 2
        port = hit[0]
    L(1, f"✅ 使用串口 {port}")

    # L2 BGAPI 后端启动
    import pygatt
    try:
        backend = pygatt.BGAPIBackend(serial_port=port)
        backend.start()
        L(2, "✅ BGAPIBackend.start() 成功（串口未被占用）")
    except Exception as e:
        L(2, f"❌ backend.start() 失败: {type(e).__name__}: {e}")
        L(2, "   → 串口可能被其他程序占用（关闭其他蓝牙工具/控制台会话后重试）")
        return 3

    try:
        # L3 扫描（addr 已给则跳过）
        if addr:
            L(3, f"直连模式：跳过扫描，目标 {addr}")
        else:
            L(3, "扫描 Muse 头环 10 秒（请确认头环开机、蓝灯、2 米内）...")
            try:
                devices = backend.scan(10, active=True)
            except Exception as e:
                L(3, f"❌ scan 异常: {type(e).__name__}: {e}")
                traceback.print_exc()
                return 4
            names = []
            for d in devices:
                nm = d.get("name") if isinstance(d, dict) else getattr(d, "name", None)
                ad = d.get("address") if isinstance(d, dict) else getattr(d, "address", None)
                names.append((nm, ad))
            L(3, f"扫到 {len(devices)} 个设备: {names[:8]}")

            def _is_muse(d):
                # 名称匹配 OR 厂商 MAC 前缀（00:55:DA = Interaxon/Muse OUI）
                nm = d.get("name") if isinstance(d, dict) else getattr(d, "name", None)
                ad = d.get("address") if isinstance(d, dict) else getattr(d, "address", None)
                return "muse" in (nm or "").lower() or (ad or "").upper().startswith("00:55:DA")

            muses = [_d_addr(d) for d in devices if _is_muse(d)]
            if not muses:
                L(3, "❌ 未发现 Muse（名称与 00:55:DA 前缀都不匹配）。检查：头环是否"
                     "开机？是否已被手机/内置蓝牙连着（被占用的头环不广播）？")
                L(3, "   可改用直连模式：bled112_diag.py 00:55:DA:BB:E8:D8")
                return 5
            addr = muses[0]
            L(3, f"✅ 目标头环 {addr}")

        # L4 连接
        device = None
        last_e = None
        for at in ("public", "random"):
            try:
                device = backend.connect(addr, address_type=at, timeout=15)
                L(4, f"✅ connect 成功（address_type={at}）")
                break
            except Exception as e:
                last_e = e
                L(4, f"   connect({at}) 失败: {type(e).__name__}: {e}")
        if device is None:
            L(4, f"❌ 两种地址类型都连不上。最后异常: {last_e}")
            return 6

        # L5 特征枚举
        try:
            chars = device.discover_characteristics()
            L(5, f"✅ 发现 {len(chars)} 个特征:")
            for h, c in chars.items():
                L(5, f"   handle={h} uuid={c.uuid} props={c.properties}")
        except Exception as e:
            L(5, f"❌ discover_characteristics 失败: {type(e).__name__}: {e}")
            traceback.print_exc()
            return 7

        # L6 订阅 EEG 通知
        from OpenMuse.muse import MuseS
        got = {"n": 0, "bytes": 0}

        def _cb(handle, value):
            got["n"] += 1
            got["bytes"] += len(value)

        try:
            device.subscribe(MuseS.EEG_UUID, _cb, False)
            L(6, f"✅ 已订阅 EEG 通知 {MuseS.EEG_UUID}")
        except Exception as e:
            L(6, f"❌ subscribe 失败: {type(e).__name__}: {e}")
            traceback.print_exc()
            return 8

        # L7 收包计数（未握手时 Muse 不发 EEG，此步仅观察自发通知）
        L(7, "等待 EEG 数据 15 秒（不发送任何控制命令，只看是否有自发通知）...")
        time.sleep(15)
        L(7, f"收到 EEG 包 {got['n']} 个 / {got['bytes']} 字节")
        if got["n"] == 0:
            L(7, "   订阅成功但零数据：Muse 未收到'开始流'控制命令时不发 EEG，"
                 "此结果符合预期，不代表故障。")
            L(7, "   继续 L8：走与控制台完全相同的 OpenMuse 握手验数据流。")
        else:
            L(7, f"✅ 有自发通知（{got['n']/15:.1f} 包/秒）。")
            return 0

        # L8 完整握手（复用控制台同一路径）+ 收包计数
        from ble_receiver import _BgapiClientAdapter
        got2 = {"n": 0, "bytes": 0}

        def _cb2(handle, value):
            got2["n"] += 1
            got2["bytes"] += len(value)

        client = _BgapiClientAdapter(device)
        callbacks = {MuseS.EEG_UUID: lambda h, v: _cb2(h, v),
                     MuseS.OTHER_UUID: lambda h, v: _cb2(h, v)}
        L(8, "执行 MuseS.connect_and_initialize（与控制台同一路径）...")
        try:
            asyncio.run(MuseS.connect_and_initialize(
                client, "p1041", callbacks, verbose=True))
            L(8, "✅ 握手成功")
        except Exception as e:
            L(8, f"❌ 握手失败: {type(e).__name__}: {e}")
            traceback.print_exc()
            L(8, "   → 这就是控制台红字'数据流静默'的根因所在层。")
            return 9
        L(8, "握手后等待 EEG 数据 15 秒...")
        time.sleep(15)
        L(8, f"收到 EEG 包 {got2['n']} 个 / {got2['bytes']} 字节")
        if got2["n"] == 0:
            L(8, "❌ 握手成功仍零数据 → 问题在订阅/通知投递层。")
            return 10
        L(8, f"✅ BLED112 全链路通（{got2['n']/15:.1f} 包/秒）。"
             "控制台侧问题在会话/看门狗层。")
        return 0
    finally:
        try:
            backend.stop()
        except Exception:
            pass

if __name__ == "__main__":
    sys.exit(main())
