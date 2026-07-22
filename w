warning: in the working copy of 'app/routes/results.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'app/static/index.html', LF will be replaced by CRLF the next time Git touches it
[1mdiff --git a/app/static/index.html b/app/static/index.html[m
[1mindex 0cc373a..9452cf6 100644[m
[1m--- a/app/static/index.html[m
[1m+++ b/app/static/index.html[m
[36m@@ -4,298 +4,740 @@[m
 <meta charset="UTF-8">[m
 <meta name="viewport" content="width=device-width, initial-scale=1.0">[m
 <title>Intake — Vehicle Image Inspection</title>[m
[31m-<meta name="description" content="Real-time vehicle image inspection dashboard. Upload images and get instant quality analysis: blur, brightness, duplicate detection, screenshot check, and plate OCR.">[m
[32m+[m[32m<meta name="description" content="Enterprise vehicle image inspection pipeline. Real-time quality and authenticity analysis: blur, brightness, duplicate detection, screenshot check, and plate OCR.">[m
 <link rel="preconnect" href="https://fonts.googleapis.com">[m
 <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">[m
 <style>[m
[31m-  :root{[m
[31m-    --bg:#14171A;[m
[31m-    --panel:#1B1F23;[m
[31m-    --panel-raised:#21262B;[m
[31m-    --border:#2A2F35;[m
[31m-    --text:#ECEEF0;[m
[31m-    --text-muted:#8B929A;[m
[31m-    --text-faint:#5B6167;[m
[31m-    --amber:#F5A623;[m
[31m-    --green:#4ADE80;[m
[31m-    --red:#E5595E;[m
[31m-    --blue:#6FA3D8;[m
[31m-    --font-display:'Space Grotesk', sans-serif;[m
[31m-    --font-body:'Inter', sans-serif;[m
[31m-    --font-mono:'JetBrains Mono', monospace;[m
[31m-  }[m
[31m-  *{box-sizing:border-box; margin:0; padding:0;}[m
[31m-  html,body{height:100%;}[m
[31m-  body{[m
[31m-    background:var(--bg);[m
[31m-    color:var(--text);[m
[31m-    font-family:var(--font-body);[m
[31m-    -webkit-font-smoothing:antialiased;[m
[31m-  }[m
[31m-  @media (prefers-reduced-motion:reduce){[m
[31m-    *{animation-duration:0.001ms !important; transition-duration:0.001ms !important;}[m
[31m-  }[m
[32m+[m[32m/* ═══════════════════════════════════════════════════════════[m
[32m+[m[32m   DESIGN TOKENS[m
[32m+[m[32m═══════════════════════════════════════════════════════════ */[m
[32m+[m[32m:root {[m
[32m+[m[32m  /* Surfaces */[m
[32m+[m[32m  --bg:            #0D1117;[m
[32m+[m[32m  --surface-1:     #161B22;[m
[32m+[m[32m  --surface-2:     #1C2128;[m
[32m+[m[32m  --surface-3:     #21262D;[m
[32m+[m[32m  --surface-4:     #272C34;[m
 [m
[31m-  /* ── Top bar ─────────────────────────────────────────────── */[m
[31m-  .topbar{[m
[31m-    display:flex; align-items:center; justify-content:space-between;[m
[31m-    padding:18px 28px;[m
[31m-    border-bottom:1px solid var(--border);[m
[31m-    background:var(--panel);[m
[31m-  }[m
[31m-  .brand{display:flex; align-items:center; gap:12px;}[m
[31m-  .brand-mark{[m
[31m-    width:30px; height:30px; border-radius:7px;[m
[31m-    background:linear-gradient(135deg, var(--amber), #d97f1a);[m
[31m-    display:flex; align-items:center; justify-content:center;[m
[31m-    font-family:var(--font-mono); font-weight:600; font-size:14px; color:#1a1200;[m
[31m-  }[m
[31m-  .brand-text h1{font-family:var(--font-display); font-size:16px; font-weight:600; letter-spacing:0.01em;}[m
[31m-  .brand-text p{font-size:11.5px; color:var(--text-muted); font-family:var(--font-mono); margin-top:1px;}[m
[31m-  .conn{display:flex; align-items:center; gap:10px;}[m
[31m-  .conn-field{[m
[31m-    display:flex; align-items:center; gap:8px;[m
[31m-    background:var(--panel-raised); border:1px solid var(--border);[m
[31m-    border-radius:8px; padding:6px 10px;[m
[31m-  }[m
[31m-  .conn-field label{font-size:10.5px; color:var(--text-faint); font-family:var(--font-mono); text-transform:uppercase; letter-spacing:0.06em;}[m
[31m-  .conn-field input{[m
[31m-    background:transparent; border:none; outline:none; color:var(--text);[m
[31m-    font-family:var(--font-mono); font-size:12.5px; width:170px;[m
[31m-  }[m
[31m-  .dot{width:7px; height:7px; border-radius:50%; background:var(--text-faint); flex-shrink:0;}[m
[31m-  .dot.ok{background:var(--green); box-shadow:0 0 6px rgba(74,222,128,0.6);}[m
[31m-  .dot.bad{background:var(--red); box-shadow:0 0 6px rgba(229,89,94,0.5);}[m
[31m-[m
[31m-  /* ── Shell ───────────────────────────────────────────────── */[m
[31m-  .shell{[m
[31m-    display:grid; grid-template-columns:360px 1fr;[m
[31m-    height:calc(100vh - 66px);[m
[31m-  }[m
[31m-  @media (max-width:860px){ .shell{grid-template-columns:1fr; height:auto;} }[m
[32m+[m[32m  /* Borders */[m
[32m+[m[32m  --border:        #30363D;[m
[32m+[m[32m  --border-subtle: #21262D;[m
 [m
[31m-  /* ── Sidebar ─────────────────────────────────────────────── */[m
[31m-  .sidebar{[m
[31m-    border-right:1px solid var(--border);[m
[31m-    display:flex; flex-direction:column;[m
[31m-    overflow:hidden;[m
[31m-  }[m
[31m-  .dropzone{[m
[31m-    margin:18px; padding:22px 16px;[m
[31m-    border:1.5px dashed var(--border);[m
[31m-    border-radius:12px;[m
[31m-    text-align:center;[m
[31m-    cursor:pointer;[m
[31m-    transition:border-color .15s ease, background .15s ease;[m
[31m-  }[m
[31m-  .dropzone:hover, .dropzone.drag{[m
[31m-    border-color:var(--amber);[m
[31m-    background:rgba(245,166,35,0.05);[m
[31m-  }[m
[31m-  .dropzone svg{width:26px; height:26px; color:var(--text-faint); margin-bottom:10px;}[m
[31m-  .dropzone p{font-size:13px; color:var(--text-muted);}[m
[31m-  .dropzone .hint{font-size:11px; color:var(--text-faint); margin-top:4px; font-family:var(--font-mono);}[m
[31m-  .dropzone input{display:none;}[m
[31m-[m
[31m-  .queue-head{[m
[31m-    display:flex; align-items:center; justify-content:space-between;[m
[31m-    padding:0 18px 10px 18px;[m
[31m-  }[m
[31m-  .queue-head h2{[m
[31m-    font-family:var(--font-mono); font-size:11px; text-transform:uppercase;[m
[31m-    letter-spacing:0.08em; color:var(--text-faint); font-weight:500;[m
[31m-  }[m
[31m-  .queue-count{[m
[31m-    font-family:var(--font-mono); font-size:11px; color:var(--text-muted);[m
[31m-    background:var(--panel-raised); border:1px solid var(--border);[m
[31m-    border-radius:20px; padding:1px 8px;[m
[31m-  }[m
[31m-  .queue{[m
[31m-    flex:1; overflow-y:auto; padding:0 12px 18px 12px;[m
[31m-    display:flex; flex-direction:column; gap:6px;[m
[31m-  }[m
[31m-  .queue::-webkit-scrollbar{width:6px;}[m
[31m-  .queue::-webkit-scrollbar-thumb{background:var(--border); border-radius:3px;}[m
[32m+[m[32m  /* Text */[m
[32m+[m[32m  --text:          #E6EDF3;[m
[32m+[m[32m  --text-secondary:#8B949E;[m
[32m+[m[32m  --text-muted:    #6E7681;[m
 [m
[31m-  .empty-state{[m
[31m-    color:var(--text-faint); font-size:12.5px; text-align:center;[m
[31m-    padding:30px 20px; line-height:1.6;[m
[31m-  }[m
[32m+[m[32m  /* Semantic accents */[m
[32m+[m[32m  --green:         #3FB950;[m
[32m+[m[32m  --green-dim:     rgba(63,185,80,0.12);[m
[32m+[m[32m  --green-border:  rgba(63,185,80,0.30);[m
[32m+[m[32m  --amber:         #E3A008;[m
[32m+[m[32m  --amber-dim:     rgba(227,160,8,0.12);[m
[32m+[m[32m  --amber-border:  rgba(227,160,8,0.30);[m
[32m+[m[32m  --red:           #F85149;[m
[32m+[m