const SCENES = {
  story: { chip: '睡不着', status: '等你决定', line: '还没睡着吗？\n我可以陪你一会儿。', note: '房间已经安静 38 分钟，你仍有翻身和轻微活动。', robot: 'idle' },
  pickup: { chip: '睡后收手机', status: '安静执行', line: '手机和灯，\n今晚交给我。', note: '已确认你稳定入睡，手机与收纳位都在安全范围。', robot: 'sleeping' },
  screen: { chip: '挡住屏幕', status: '有点执着', line: '已经很晚了。\n这次真的要睡了。', note: '已过睡眠时间 42 分钟，手机仍持续亮屏。', robot: 'idle' }
};

const DEVICES = [
  {id:'camera', name:'床头相机', detail:'画面仅在本地识别，不保存卧室视频', state:'在线', icon:'camera'},
  {id:'arm', name:'六轴机械臂', detail:'安全区正常，急停按钮可用', state:'可执行', icon:'arm'},
  {id:'light', name:'床头灯', detail:'红外控制已连接，当前亮度 18%', state:'在线', icon:'light'},
  {id:'pressure', name:'床垫压力传感器', detail:'已检测到在床状态，信号稳定', state:'在线', icon:'pressure'},
  {id:'speaker', name:'角色声音', detail:'音量已限制为夜间 24%', state:'可播放', icon:'speaker'},
  {id:'blanket', name:'拉被子能力', detail:'等待硬件安全评估，本次仅保留灯光唤醒', state:'未开放', icon:'shield', off:true}
];

const INITIAL_MEMORIES = [
  {id:1, title:'通常在 00:10 前准备睡觉', body:'超过这个时间仍在使用手机时，先温柔提醒一次。', source:'来自你过去 7 晚的选择'},
  {id:2, title:'更喜欢没有情节冲突的故事', body:'优先选择自然、旅行和微小日常，不讲悬疑内容。', source:'来自你在 8 月 26 日的对话'},
  {id:3, title:'收手机不需要叫醒我', body:'稳定入睡后可自动执行；如果位置不确定，直接跳过。', source:'由你在主动性设置中确认'}
];

function TonightPage({ scene, setScene, action, setAction, progress, paused, setPaused, showEvidence, setShowEvidence, onToast, characterMotion }) {
  const data = SCENES[scene];
  const start = () => { setAction('executing'); onToast(scene==='story'?'故事已经开始，音量会慢慢降低':'已开始执行，随时可以停止'); };
  const stop = () => { setAction('stopped'); onToast('已停止，机械臂正在安全复位'); };
  const reject = () => { setAction('rejected'); onToast('知道了，今晚不会再次打扰你'); };
  const robotState = action==='executing' ? (scene==='story'?'story':'executing') : data.robot;
  const actionName = scene==='story'?'正在讲「山谷里的慢邮局」':scene==='pickup'?'正在把手机移到收纳位':'毛绒头正在缓慢挡屏';
  return <main data-screen-label="今晚">
    <PageIntro eyebrow="Tonight · 00:48" title="今晚，我守着。" subtitle="我会把看见的事实、做出的判断和每一步动作都告诉你。" />
    <section className="companion-card" aria-label="角色当前状态">
      <div className="companion-copy"><div className="status-pill"><span className="status-dot"></span>{action==='executing'?'正在执行':action==='complete'?'已经完成':data.status}</div>
        <p className="companion-line">{action==='complete'?'今晚也替你收好啦。':data.line.split('\n').map((t,i)=><React.Fragment key={t}>{t}{i===0&&<br/>}</React.Fragment>)}</p>
        <p className="companion-note">{data.note}</p>
      </div><Robot state={robotState} motion={characterMotion}/>
    </section>

    <div className="scenario-row" aria-label="演示场景">{Object.entries(SCENES).map(([id,s])=><button key={id} className={`choice-chip ${scene===id?'active':''}`} onClick={()=>{setScene(id);setAction('suggestion');}}>{s.chip}</button>)}</div>

    <div className="section-label"><h2>今晚的时间线</h2><span>状态与真实动作同步</span></div>
    <div className="timeline">
      <div className="timeline-item"><div className="timeline-dot"></div><div className="timeline-card">
        <div className="timeline-meta"><span>观察到的事实</span><span>00:43</span></div><div className="timeline-title">还没有进入稳定睡眠</div><p className="timeline-text">光线较暗、人在床上，但仍有间歇活动。</p>
        <button className="evidence-toggle" onClick={()=>setShowEvidence(!showEvidence)}>{showEvidence?'收起依据':'发生了什么'}</button>
        {showEvidence&&<div className="evidence-grid"><div className="evidence"><b>00:43</b><span>已过入睡时间</span></div><div className="evidence"><b>18%</b><span>床头灯亮度</span></div><div className="evidence"><b>在床</b><span>压力信号稳定</span></div><div className="evidence"><b>{scene==='pickup'?'已熄屏':'仍有活动'}</b><span>手机状态</span></div></div>}
      </div></div>
      <div className="timeline-item"><div className="timeline-dot accent"></div><div>
        {action==='suggestion'&&<div className="decision-card"><div className="decision-kicker">我的建议</div><h3 className="decision-title">{scene==='story'?'让我陪你慢慢安静下来':scene==='pickup'?'我来完成今晚的睡前收尾':'让我暂时挡住这块屏幕'}</h3><p className="decision-copy">{scene==='story'?'先讲一个节奏很慢的故事。你可以暂停、换一个，或者随时让我停下。':scene==='pickup'?'手机会被放到固定收纳位，再关闭床头灯。动作不会跨过身体。':'先提醒，再在有限范围内跟随；你一拒绝，我就复位。'}</p><div className="decision-options"><span className="decision-option">{scene==='story'?'自然故事':'缓慢动作'}</span><span className="decision-option">夜间音量</span><span className="decision-option">随时停止</span></div><button className="primary-button" onClick={start}>{scene==='story'?'好，陪我一会儿':'允许这次行动'}</button><div className="text-actions"><button className="text-button" onClick={()=>onToast('10 分钟后我会再轻声问一次')}>稍后提醒</button><button className="text-button" onClick={reject}>现在不需要</button></div></div>}
        {action==='executing'&&<div className="progress-card"><div className="progress-head"><strong>{actionName}</strong><span className="progress-percent">{progress}%</span></div><div className="progress-track"><div className="progress-fill" style={{width:`${progress}%`}}></div></div><div className="progress-caption">{paused?'已暂停，机械臂保持在安全位置':scene==='story'?'嘴部动作和声音正在同步，音量会在结尾淡出':'已持续检查安全区域与停止条件'}</div><div className="control-row"><button className="control-button" onClick={()=>setPaused(!paused)}><Icon name={paused?'play':'pause'} size={15}/> {paused?'继续':'暂停'}</button><button className="control-button danger" onClick={stop}><Icon name="stop" size={14}/> 立即停止</button></div></div>}
        {action==='complete'&&<div className="timeline-card"><div className="timeline-meta"><span>已完成</span><span>00:51</span></div><div className="timeline-title">目标结果已经确认</div><p className="timeline-text">{scene==='story'?'故事已自然结束，房间活动逐渐安静。':scene==='pickup'?'手机已到固定收纳位，床头灯已经关闭。':'手机已放下，毛绒头已回到守夜位置。'}</p><button className="evidence-toggle" onClick={()=>{setAction('suggestion');onToast('演示状态已重置');}}>重新演示</button></div>}
        {(action==='stopped'||action==='rejected')&&<div className="timeline-card"><div className="timeline-meta"><span>{action==='rejected'?'尊重你的选择':'已安全停止'}</span><span>刚刚</span></div><div className="timeline-title">{action==='rejected'?'今晚不再主动介入':'机械臂正在回到待机位置'}</div><p className="timeline-text">没有动作会在你停止后继续执行。</p><button className="evidence-toggle" onClick={()=>setAction('suggestion')}>重新选择</button></div>}
      </div></div>
    </div>
  </main>;
}

function DevicesPage({ expanded, setExpanded, onToast }) {
  return <main data-screen-label="设备"><PageIntro eyebrow="Devices" title="都准备好了。" subtitle="只有会影响当前功能的异常，才会打扰你。所有物理动作都能被立即停止。"/>
    <div className="panel-card"><div className="list-row"><div className="list-icon"><Icon name="check"/></div><div className="list-main"><strong>5 项能力可用</strong><span>安全区、急停与设备连接刚刚检查完成</span></div><div className="availability"><i></i>正常</div></div></div>
    {DEVICES.map(d=><div className="panel-card" key={d.id}><div className="list-row"><div className="list-icon"><Icon name={d.icon}/></div><div className="list-main"><strong>{d.name}</strong><span>{d.detail}</span></div><div className={`availability ${d.off?'off':''}`}><i></i>{d.state}</div><button className="row-action" onClick={()=>setExpanded(expanded===d.id?null:d.id)} aria-label={`查看${d.name}详情`}><Icon name="chevron" size={17}/></button></div>{expanded===d.id&&<div className="device-details">{d.off?'该能力不会出现在真实执行流程中。安全评估通过后，需要你再次确认才能开放。':'最近检查：刚刚。连接稳定，当前没有需要处理的异常。'}<br/><button className="evidence-toggle" onClick={()=>onToast(`${d.name}检查完成`)}>再次检查</button></div>}</div>)}
  </main>;
}

function MemoryPage({ memories, setMemories, onToast }) {
  const edit = (m) => { const next = window.prompt('修改这条记忆', m.body); if(next&&next.trim()){setMemories(memories.map(x=>x.id===m.id?{...x,body:next.trim()}:x));onToast('记忆已更新');} };
  return <main data-screen-label="记忆"><PageIntro eyebrow="Memory" title="我记得，但不自作主张。" subtitle="每条偏好都说明来源。你可以随时修改或删除，不需要解释原因。"/>
    {memories.length===0&&<div className="empty-state">这里暂时没有保留的睡眠偏好。</div>}
    {memories.map(m=><div className="panel-card memory-card" key={m.id}><div className="list-row"><div className="list-icon"><Icon name="memory"/></div><div className="list-main"><strong>{m.title}</strong><span>{m.body}</span></div></div><div className="memory-source">{m.source}</div><div className="memory-actions"><button onClick={()=>edit(m)}>编辑</button><button onClick={()=>{setMemories(memories.filter(x=>x.id!==m.id));onToast('这条记忆已删除');}}>删除</button></div></div>)}
    <button className="primary-button" onClick={()=>{setMemories([...memories,{id:Date.now(),title:'新增的睡眠偏好',body:'点击编辑，把它改成你希望我记住的内容。',source:'由你刚刚手动添加'}]);onToast('已添加一条可编辑记忆');}}><Icon name="plus" size={15}/> 添加一条偏好</button>
  </main>;
}

function ProfilePage({ mode, setMode, camera, setCamera, onToast }) {
  const modeCopy={安静:'只响应你的主动指令，不主动询问。',平衡:'重要场景先询问，安全的睡后收尾可自动执行。',积极:'在更多场景主动提醒，但仍会先征得同意。'};
  return <main data-screen-label="我的"><PageIntro eyebrow="Control" title="主动，但边界由你定。" subtitle="拒绝、停止、关闭摄像头，都不会影响你继续使用其他能力。"/>
    <div className="panel-card"><div className="section-label" style={{margin:'0 0 12px'}}><h2>主动程度</h2><span>当前：{mode}</span></div><div className="mode-control">{['安静','平衡','积极'].map(m=><button key={m} className={`mode-button ${mode===m?'active':''}`} onClick={()=>{setMode(m);onToast(`主动程度已设为${m}`);}}>{m}</button>)}</div><p className="page-subtitle">{modeCopy[mode]}</p></div>
    <div className="panel-card"><div className="privacy-row"><div className="list-row" style={{minHeight:0}}><div className="list-icon"><Icon name="camera"/></div><div className="list-main"><strong>床头相机</strong><span>{camera?'仅本地识别，不保存原始画面':'已关闭，物理动作不会自动启动'}</span></div></div><button className={`switch ${camera?'on':''}`} onClick={()=>{setCamera(!camera);onToast(camera?'摄像头已关闭':'摄像头已开启');}} role="switch" aria-checked={camera} aria-label="摄像头开关"></button></div></div>
    <div className="panel-card"><div className="list-row"><div className="list-icon"><Icon name="shield"/></div><div className="list-main"><strong>设备访问与安全</strong><span>相机、机械臂、灯光与声音权限</span></div><button className="row-action" onClick={()=>onToast('所有物理动作均已启用急停保护')}><Icon name="chevron" size={17}/></button></div></div>
    <div className="panel-card"><div className="list-row"><div className="list-icon"><Icon name="clock"/></div><div className="list-main"><strong>主动行动记录</strong><span>过去 7 天主动询问 4 次，自动收尾 2 次</span></div><button className="row-action" onClick={()=>onToast('最近一次：昨晚 00:36 收好手机并关灯')}><Icon name="chevron" size={17}/></button></div></div>
  </main>;
}

function App() {
  const [t, setTweak] = useTweaks(window.TWEAK_DEFAULTS);
  const [tab,setTab]=React.useState('tonight'); const [scene,setScene]=React.useState('story');
  const [action,setAction]=React.useState('suggestion'); const [progress,setProgress]=React.useState(12); const [paused,setPaused]=React.useState(false);
  const [evidence,setEvidence]=React.useState(false); const [expanded,setExpanded]=React.useState(null); const [memories,setMemories]=React.useState(INITIAL_MEMORIES);
  const [mode,setMode]=React.useState('平衡'); const [camera,setCamera]=React.useState(true); const [input,setInput]=React.useState(''); const [listening,setListening]=React.useState(false);
  const [toast,setToast]=React.useState('');
  const onToast=React.useCallback(msg=>{setToast(msg);window.clearTimeout(window.__toastTimer);window.__toastTimer=window.setTimeout(()=>setToast(''),2200);},[]);

  React.useEffect(()=>{ if(action!=='executing'||paused)return; const id=setInterval(()=>setProgress(p=>{if(p>=100){setAction('complete');return 100;}return Math.min(100,p+7);}),800); return()=>clearInterval(id); },[action,paused]);
  React.useEffect(()=>{setProgress(12);setPaused(false);},[scene,action==='suggestion']);
  React.useEffect(()=>{document.documentElement.style.setProperty('--accent',t.palette[0]);document.documentElement.style.setProperty('--ink',t.palette[1]);document.documentElement.style.setProperty('--paper',t.palette[2]);document.documentElement.style.setProperty('--space',t.density==='紧凑'?'13px':t.density==='宽松'?'24px':'18px');},[t]);

  const send=()=>{const q=input.trim();if(!q)return;if(q.includes('停止')){setAction('stopped');onToast('已停止当前动作');}else if(q.includes('故事')){setScene('story');setAction('executing');setTab('tonight');onToast('好，我讲一个很慢的故事');}else if(q.includes('收手机')){setScene('pickup');setAction('executing');setTab('tonight');onToast('开始检查手机与安全区域');}else if(q.includes('放松')){setScene('story');setAction('suggestion');setTab('tonight');onToast('我准备了一个低刺激的放松方案');}else{onToast('我听见了，会结合今晚的状态再决定');}setInput('');};
  const navigate=(id)=>{setTab(id);setExpanded(null);};
  return <div className="stage"><div className="phone-shell">
    <div className={`toast ${toast?'show':''}`}>{toast}</div>
    <div className="app-scroll"><Topbar onSettings={()=>navigate('profile')}/>
      {tab==='tonight'&&<TonightPage scene={scene} setScene={setScene} action={action} setAction={setAction} progress={progress} paused={paused} setPaused={setPaused} showEvidence={evidence} setShowEvidence={setEvidence} onToast={onToast} characterMotion={t.characterMotion}/>} 
      {tab==='devices'&&<DevicesPage expanded={expanded} setExpanded={setExpanded} onToast={onToast}/>} 
      {tab==='memory'&&<MemoryPage memories={memories} setMemories={setMemories} onToast={onToast}/>} 
      {tab==='profile'&&<ProfilePage mode={mode} setMode={setMode} camera={camera} setCamera={setCamera} onToast={onToast}/>} 
    </div>
    {tab==='tonight'&&<Composer value={input} setValue={setInput} onSend={send} listening={listening} onListen={()=>{setListening(!listening);onToast(listening?'已停止聆听':'请说“讲个故事”或“停止”');}}/>}
    <BottomNav active={tab} onChange={navigate}/>
    <TweaksPanel title="风格"><TweakSection label="界面"/><TweakColor label="配色" value={t.palette} options={[["#e95a36","#242522","#e9e5dd"],["#d04c72","#272329","#ece6e7"],["#3f725b","#1f2924","#e5e6df"]]} onChange={v=>setTweak('palette',v)}/><TweakRadio label="信息密度" value={t.density} options={['紧凑','舒展','宽松']} onChange={v=>setTweak('density',v)}/><TweakToggle label="角色动效" value={t.characterMotion} onChange={v=>setTweak('characterMotion',v)}/></TweaksPanel>
  </div></div>;
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
