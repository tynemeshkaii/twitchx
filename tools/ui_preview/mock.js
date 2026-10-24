// Stub for window.pywebview.api plus fake data. window.__boot(opts) plays the
// role of Python: pushes config and a streams update.
// opts: {empty, loggedOut, noStreams, allOffline, long}.
// window.__scenario.* opens views that need extra callbacks (browse/channel/player).
(function(){
  const pal = [['#7c3aed','#f472b6'],['#0ea5e9','#22d3ee'],['#f97316','#facc15'],['#10b981','#84cc16'],['#ef4444','#f97316'],['#6366f1','#06b6d4'],['#db2777','#9333ea'],['#14b8a6','#3b82f6'],['#eab308','#ef4444']];
  function thumb(i, label){
    const [a,b]=pal[i%pal.length];
    return 'data:image/svg+xml;utf8,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="440" height="248"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs><rect width="440" height="248" fill="url(#g)"/><circle cx="${100+i*37%240}" cy="${80+i*23%100}" r="70" fill="#fff" opacity=".12"/><rect x="0" y="170" width="440" height="78" fill="#000" opacity=".18"/><text x="24" y="140" font-family="Helvetica" font-weight="700" font-size="34" fill="#fff" opacity=".85">${label}</text></svg>`);
  }
  function avatar(i, ch){
    const [a,b]=pal[(i+3)%pal.length];
    return 'data:image/svg+xml;utf8,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs><rect width="64" height="64" fill="url(#g)"/><text x="32" y="42" text-anchor="middle" font-family="Helvetica" font-weight="700" font-size="28" fill="#fff">${ch}</text></svg>`);
  }
  const now = Date.now();
  const live = [
    ['shroud','shroud','twitch','VALORANT','ranked grind w/ the boys — !socials !merch',42100],
    ['xqc','xQc','kick','Just Chatting','REACTING TO EVERYTHING | JUICER HOURS | !kick',88300],
    ['pokimane','pokimane','twitch','Minecraft','cozy hardcore day 12 :3',15400],
    ['asmongold','Asmongold','twitch','World of Warcraft','MIDNIGHT EXPANSION RACE — HC raid prog',61200],
    ['adinross','Adin Ross','kick','Just Chatting','IRL in Miami today',33900],
    ['lirik','LIRIK','twitch','Elden Ring Nightreign','first time with chat',12800],
    ['UCX6OQ3DkcsbYNE6H8uQQuVA','MrBeast Gaming','youtube','Fortnite','$100,000 Fortnite Tournament LIVE',210000],
    ['summit1g','summit1g','twitch','Escape from Tarkov','wipe day. no sleep.',9700],
    ['trainwreckstv','Trainwreckstv','kick','Slots & Casino','big stuff',21500],
  ];
  const offline = [['hasanabi','HasanAbi','twitch'],['tarik','tarik','twitch'],['ludwig','ludwig','youtube'],['amouranth','Amouranth','kick'],['sodapoppin','sodapoppin','twitch']];
  const meta = {}; const favs = [];
  live.concat(offline).forEach(r => { meta[r[2]+':'+r[0]] = {login:r[0], platform:r[2], display_name:r[1]}; favs.push(r[0]); });
  const streams = live.map((r,i)=>({login:r[0],display_name:r[1],platform:r[2],game:r[3],title:r[4],viewers:r[5],started_at:new Date(now-(i*47+30)*60000).toISOString(),thumbnail_url:'x',viewer_trend:null}));
  const idx = {}; live.concat(offline).forEach((r,i)=> idx[r[2]+':'+r[0]] = i);
  const api = new Proxy({}, { get(t,k){
    if (k==='then') return undefined;
    return function(){
      const a = arguments;
      if (k==='get_avatar') setTimeout(()=>{ const key=a[1]+':'+a[0]; const r=live.concat(offline)[idx[key]]; window.onAvatar({login:a[0],platform:a[1],data:avatar(idx[key]||0,(r?r[1]:a[0])[0].toUpperCase())}); },10);
      if (k==='search_channels') setTimeout(()=>{ const q=String(a[0]).toLowerCase(); window.onSearchResults([
        {login:'shroud',display_name:'shroud',platform:'twitch',is_live:true,game_name:'VALORANT'},
        {login:'shahzam',display_name:'ShahZaM',platform:'twitch',is_live:false,game_name:'Counter-Strike 2'},
        {login:'sharishaxd',display_name:'SharishaxD',platform:'kick',is_live:true,game_name:'Just Chatting'},
      ].filter(r=>r.login.indexOf(q)!==-1), {query:a[0],platform:a[1]}); },50);
      if (k==='get_thumbnail') setTimeout(()=>{ const i=idx[a[0]]; window.onThumbnail({login:a[0],data:thumb(i,live[i][3])}); },10);
      return Promise.resolve(null);
    };
  }});
  window.__fake = {streams, favs, meta, thumb, avatar, live};

  // Worst-case data: a 140-char title, 25-char names, 50 favorites, 1.2M viewers.
  function longData(){
    const title = 'EXTREMELY LONG STREAM TITLE that keeps going — day 47 of the 24/7 subathon, every sub adds a minute, !socials !merch !discord !sponsor';
    const lStreams = streams.map(function(st, i){
      const o = Object.assign({}, st);
      if (i === 0) { o.title = title.slice(0, 140); o.viewers = 1200000; o.display_name = 'TheVeryLongestChannelName'; o.game = 'Grand Theft Auto V: Enhanced Edition'; }
      if (i === 1) { o.display_name = 'xX_ProGamerUltimate420_Xx'; o.title = title.slice(0, 140); }
      return o;
    });
    const lFavs = favs.slice(); const lMeta = Object.assign({}, meta);
    for (let i = 0; lFavs.length < 50; i++) {
      const login = 'offline_channel_name_' + String(i).padStart(4, '0');
      lFavs.push(login);
      lMeta['twitch:' + login] = {login: login, platform: 'twitch', display_name: login.slice(0, 25)};
    }
    lMeta[lStreams[0].platform + ':' + lStreams[0].login] = Object.assign({}, lMeta[lStreams[0].platform + ':' + lStreams[0].login], {display_name: lStreams[0].display_name});
    lMeta[lStreams[1].platform + ':' + lStreams[1].login] = Object.assign({}, lMeta[lStreams[1].platform + ':' + lStreams[1].login], {display_name: lStreams[1].display_name});
    return {streams: lStreams, favs: lFavs, meta: lMeta};
  }

  window.__boot = function(opts){
    opts = opts||{};
    window.pywebview = {api};
    window.dispatchEvent(new Event('pywebviewready'));
    let d = {streams: streams, favs: favs, meta: meta};
    if (opts.long) d = longData();
    if (opts.empty) d = {streams: [], favs: [], meta: {}};
    if (opts.allOffline) d = {streams: [], favs: d.favs, meta: d.meta};
    window.onConfigLoaded({version:'0.9.0',has_credentials:true,youtube_enabled:true,
      current_user: opts.loggedOut?null:{login:'tynemesh',display_name:'tynemesh'},
      kick_user: opts.loggedOut?null:{login:'tyne',display_name:'tyne'},
      favorites: d.favs, favorites_meta: d.meta, settings:{quality:'best'}, pip_enabled:true});
    if (!opts.noStreams) window.onStreamsUpdate({streams: d.streams, favorites: d.favs, favorites_meta: d.meta, updated_time:'15:42:07', total_viewers: d.streams.length ? (opts.long ? 1694900 : 494900) : 0, total_viewers_formatted: d.streams.length ? (opts.long ? '1.7M' : '495K') : '0', has_credentials:true, user_avatars:{}});
  };
  window.__scenario = {
    // ── States (phase 4.4) ──────────────────────────────
    'state-skeleton': function() { TwitchX.showSkeletonGrid(); },
    'state-browse-loading': function() { TwitchX.showBrowseView(); },
    'state-vods-loading': function() {
      window.__scenario.channel();
      TwitchX.switchChannelTab(document.getElementById('channel-tab-vods-btn'), 'vods');
    },
    'state-error-toast': function() {
      window.onStatusUpdate({ type: 'error', text: 'Twitch API error: 401 Unauthorized — sign in again in Accounts' });
    },
    'state-player-error': function() {
      window.__scenario.player();
      document.querySelectorAll('.toast').forEach(function(t) { t.remove(); });
      TwitchX.showPlayerError('Playback failed', 'The stream ended or the network dropped. Retry, or open it in IINA.');
    },
    'state-browse-errors': function() {
      TwitchX.showBrowseView();
      window.onBrowseCategories({ items: [], errors: { twitch: 'HTTP 401', kick: 'timed out', youtube: 'quota exceeded' } });
    },
    'state-browse-empty': function() {
      TwitchX.showBrowseView();
      window.onBrowseCategories({ items: [], errors: {} });
    },
    'state-channel-offline': function() {
      TwitchX.showChannelView('hasanabi', 'twitch');
      window.onChannelProfile({ login: 'hasanabi', display_name: 'HasanAbi', platform: 'twitch', bio: 'Political commentary and react content.', followers: 2900000, is_live: false, watch_supported: true, avatar_url: avatar(9, 'H'), can_follow: true });
    },
    'state-stale': function() {
      window.onStatusUpdate({ type: 'warn', text: 'Twitch did not respond — showing data from 15:42', stale: true });
    },
    'state-long': function() {
      TwitchX.state.sidebarSections.offline = false;
      TwitchX.renderSidebar();
    },
    browse: function() {
      TwitchX.showBrowseView();
      const cats = ['Just Chatting','VALORANT','League of Legends','Fortnite','Minecraft','GTA V','Counter-Strike 2','Elden Ring','Slots','World of Warcraft'];
      window.onBrowseCategories(cats.map(function(n, i) {
        return { name: n, box_art_url: null, viewers: 300000 - i * 20000, platforms: i % 3 ? ['twitch','kick'] : ['twitch','kick','youtube'] };
      }));
    },
    'browse-streams': function() {
      TwitchX.showBrowseView();
      TwitchX._triggerBrowseTopStreams({ name: 'VALORANT' });
      window.onBrowseTopStreams({ category: 'VALORANT', streams: live.slice(0, 6).map(function(r, i) {
        return { channel_login: r[0], display_name: r[1], platform: r[2], title: r[4], viewers: r[5], category: 'VALORANT', thumbnail_url: thumb(i, 'VALORANT'), started_at: new Date(now - (i * 53 + 20) * 60000).toISOString() };
      }) });
    },
    'channel-vods': function() {
      window.__scenario.channel();
      const btn = document.getElementById('channel-tab-vods-btn');
      TwitchX.switchChannelTab(btn, 'vods');
      window.onChannelMedia({ tab: 'vods', login: 'shroud', platform: 'twitch', items: [0, 1, 2, 3].map(function(i) {
        return { title: ['Ranked to Radiant day 4', 'Tarkov wipe, part 2', 'Late night aim training', 'Viewer games'][i], url: 'https://example.com/' + i, thumbnail_url: thumb(i + 2, 'VOD'), duration_seconds: 3600 * (i + 2) + 640, published_at: new Date(now - i * 86400000).toISOString(), views: 120000 - i * 21000, platform: 'twitch' };
      }) });
    },
    channel: function() {
      TwitchX.showChannelView('shroud', 'twitch');
      window.onChannelProfile({ login: 'shroud', display_name: 'shroud', platform: 'twitch', bio: 'Former CS pro, full-time streamer.', followers: 11200000, is_live: true, watch_supported: true, avatar_url: avatar(0, 'S'), can_follow: true });
    },
    player: function() {
      window.onStreamReady({ url: '', channel: 'shroud', platform: 'twitch', title: 'ranked grind w/ the boys — !socials !merch', has_chat: true });
      if (document.activeElement) document.activeElement.blur();
      const names = [['Nightbot','#9147ff'],['vexx','#ff7f50'],['kirra','#1e90ff'],['dumbo','#2e8b57'],['glizzy','#daa520'],['ttv_mike','#ff69b4']];
      const texts = ['Welcome to the stream!','that flick was insane','LUL','what sens are you on','W stream','first time here','!socials','clip it','KEKW','what crosshair?','gg','LETSGO'];
      for (let i = 0; i < 24; i++) {
        const n = names[i % names.length];
        window.onChatMessage({ platform: 'twitch', channel_id: 'shroud', author: n[0].toLowerCase(), author_display: n[0], author_color: n[1], badges: [], text: texts[i % texts.length], timestamp: new Date().toISOString(), emotes: [] });
      }
    },
  };
})();
