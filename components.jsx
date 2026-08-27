function Icon({ name, size = 20, stroke = 1.8 }) {
  const paths = {
    moon: <><path d="M20 15.1A8 8 0 0 1 8.9 4 8 8 0 1 0 20 15.1Z" /></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.82 2.82-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.04 1.55V21h-4v-.09A1.7 1.7 0 0 0 9 19.36a1.7 1.7 0 0 0-1.88.34l-.06.06-2.82-2.82.06-.06A1.7 1.7 0 0 0 4.64 15 1.7 1.7 0 0 0 3.09 14H3v-4h.09A1.7 1.7 0 0 0 4.64 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.82-2.82.06.06A1.7 1.7 0 0 0 9 4.64 1.7 1.7 0 0 0 10 3.09V3h4v.09A1.7 1.7 0 0 0 15 4.64a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.82 2.82-.06.06A1.7 1.7 0 0 0 19.36 9 1.7 1.7 0 0 0 20.91 10H21v4h-.09A1.7 1.7 0 0 0 19.4 15Z"/></>,
    devices: <><rect x="5" y="3" width="14" height="18" rx="3"/><path d="M9 17h6M9 7h6"/></>,
    memory: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4H6.5A2.5 2.5 0 0 0 4 6.5v13Z"/><path d="M8 7h7M8 11h5"/></>,
    user: <><circle cx="12" cy="8" r="4"/><path d="M4.5 21a7.5 7.5 0 0 1 15 0"/></>,
    camera: <><path d="M15 8.5 20 6v12l-5-2.5"/><rect x="3" y="5" width="12" height="14" rx="2"/></>,
    arm: <><circle cx="8" cy="16" r="2.5"/><circle cx="15" cy="8" r="2.5"/><path d="m9.7 14.1 3.6-4.2M17 10l3 4v5M17 19h5M5.5 18.5 3 21h10"/></>,
    light: <><path d="M9 18h6M10 22h4"/><path d="M8 14a6 6 0 1 1 8 0c-1 .8-1 1.5-1 2H9c0-.5 0-1.2-1-2Z"/></>,
    pressure: <><path d="M4 16c3-4 5-5 8-5s5 1 8 5"/><path d="M7 19h10M12 11V4M9 6l3-2 3 2"/></>,
    speaker: <><path d="M11 5 6 9H3v6h3l5 4V5Z"/><path d="M15 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12"/></>,
    chevron: <path d="m9 18 6-6-6-6"/>,
    mic: <><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></>,
    send: <><path d="m22 2-7 20-4-9-9-4 20-7Z"/><path d="M22 2 11 13"/></>,
    pause: <><path d="M8 5v14M16 5v14"/></>,
    play: <path d="m8 5 11 7-11 7V5Z"/>,
    stop: <rect x="6" y="6" width="12" height="12" rx="2"/>,
    check: <path d="m5 12 4 4L19 6"/>,
    shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    plus: <path d="M12 5v14M5 12h14"/>
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function Robot({ state, motion = true }) {
  const stateClass = state === 'executing' ? 'executing' : state === 'story' ? 'story' : state === 'sleeping' ? 'sleeping' : '';
  return <div className={`robot ${motion ? stateClass : ''}`} aria-label="晚安搭子机械臂角色">
    <div className="robot-arm">
      <div className="base"></div><div className="arm-segment arm-lower"></div><div className="joint"></div><div className="arm-segment arm-upper"></div>
      <div className="head"><span className="eye left"></span><span className="eye right"></span><span className="mouth"></span></div>
    </div>
  </div>;
}

function Topbar({ onSettings }) {
  return <header className="topbar">
    <div className="brand-lockup">
      <div className="brand-mark"><Icon name="moon" size={19}/></div>
      <div><div className="brand-name">晚安搭子</div><div className="brand-status">在你需要时，轻轻推一把</div></div>
    </div>
    <button className="icon-button" onClick={onSettings} aria-label="打开设置"><Icon name="settings" /></button>
  </header>;
}

function BottomNav({ active, onChange }) {
  const items = [['tonight','moon','今晚'],['devices','devices','设备'],['memory','memory','记忆'],['profile','user','我的']];
  return <nav className="bottom-nav" aria-label="主导航">{items.map(([id, icon, label]) =>
    <button key={id} className={`nav-button ${active===id?'active':''}`} onClick={() => onChange(id)} aria-current={active===id?'page':undefined}>
      <span className="nav-glyph"><Icon name={icon} size={19}/></span><span>{label}</span>
    </button>
  )}</nav>;
}

function Composer({ value, setValue, onSend, listening, onListen }) {
  return <div className="composer-wrap"><div className="composer">
    <button className={`composer-button ${listening?'listening':''}`} onClick={onListen} aria-label={listening?'停止聆听':'语音输入'}><Icon name="mic" size={18}/></button>
    <input value={value} onChange={e=>setValue(e.target.value)} onKeyDown={e=>{if(e.key==='Enter') onSend();}} placeholder={listening?'我在听…':'说“讲个故事”或“停止”'} />
    <button className="send-button" onClick={onSend} aria-label="发送"><Icon name="send" size={17}/></button>
  </div></div>;
}

function PageIntro({ eyebrow, title, subtitle }) {
  return <div className="page-intro"><p className="eyebrow">{eyebrow}</p><h1 className="page-title">{title}</h1><p className="page-subtitle">{subtitle}</p></div>;
}

Object.assign(window, { Icon, Robot, Topbar, BottomNav, Composer, PageIntro });
