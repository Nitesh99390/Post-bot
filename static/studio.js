'use strict';
// Inline SVGs avoid icon-library downloads and remain crisp at any display scale.
const icons = {
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
  moon: '<path d="M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
  'arrow-up': '<path d="M6 18 18 6M6 6h12v12"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z M22 2 11 13"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
  refresh: '<path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/>',
  code: '<path d="m8 6-6 6 6 6M16 6l6 6-6 6M14 3l-4 18"/>',
  'double-check': '<path d="m2 12 4 4 9-9M10 14l2 2 9-9"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  layers:'<rect x="6" y="3" width="14" height="16" rx="3"/><path d="M16 22H6a3 3 0 0 1-3-3V8M10 8h6M10 12h6"/>',
  user:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  award:'<circle cx="12" cy="8" r="5"/><path d="m8 13-2 8 6-3 6 3-2-8M10 8l1.5 1.5L14 7"/>',
  plus:'<path d="M12 5v14M5 12h14"/>', arrow:'<path d="M4 12h15m-5-5 5 5-5 5"/>', chevron:'<path d="m9 5 7 7-7 7"/>', 'chevron-down':'<path d="m6 9 6 6 6-6"/>',
  image:'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-5-5L5 21"/>',
  'image-plus':'<path d="M21 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8M21 3v6M18 6h6M3 17l5-5 4 4 4-4 5 5"/><circle cx="8" cy="8" r="1"/>',
  cloud:'<path d="M7 18a5 5 0 1 1 .7-9.95A7 7 0 0 1 21 11a3.5 3.5 0 0 1-1 7H7Z"/>',
  shield:'<path d="M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7l-9-4Z"/><path d="m8 12 3 3 5-6"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  check:'<path d="m5 12 4 4L19 6"/>', 'check-circle':'<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>', more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  help:'<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 .5c0 1.5-2.5 1.5-2.5 3M12 16h.01"/>',
  sparkles:'<path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3ZM20 2v4M18 4h4"/>',
  bulb:'<path d="M9 18v-2a6 6 0 1 1 6 0v2M9 18h6M10 21h4"/>',
  search:'<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/>',
  text:'<path d="M4 5h16M12 5v15M8 20h8"/>', calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 11h18"/>',
};
const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.layers}</svg>`;
function hydrateIcons(root=document){ $$('[data-icon]',root).forEach(node=>{node.innerHTML=icon(node.dataset.icon);}); }
hydrateIcons();
const tg = window.Telegram?.WebApp;
const initData = tg?.initData || '';
const demo = document.body.dataset.demo === 'true' && !initData;
const state = {posts:[], profile:null, leaderboard:[], page:0, hasMore:false, filter:'all', activePage:'overview', busy:false, photoURL:null, photoCache:new Map(), mediaJobs:new Map(), ready:false, loading:false, selectedPost:null, submissionKey:null};
const headers = {'X-Telegram-Init-Data': initData};
try{tg?.ready();tg?.expand();if(tg?.isVersionAtLeast?.('6.1')){tg.setHeaderColor('#f8f9fc');tg.setBackgroundColor('#f8f9fc');}}catch(_){/* Older Telegram clients use safe defaults. */}
function haptic(){try{if(tg?.isVersionAtLeast?.('6.1'))tg.HapticFeedback?.selectionChanged();}catch(_){}}
const pageInfo = {
  overview:['Overview','YOUR SPACE TO CREATE','A little inspiration. A lot of possibility.','Bring your ideas to life, one great post at a time.'],
  posts:['My posts','EVERY IDEA HAS A HOME','Your personal collection.','The photos, thoughts, and stories you’ve made your own.'],
  community:['Leaderboard','GOOD THINGS ARE BETTER TOGETHER','Meet the makers.','A community of creators with something to share.'],
  profile:['My profile','THIS SPACE BELONGS TO YOU','The person behind the posts.','Your Telegram identity. Your own little corner of the internet.']
};
function navigate(page, updateHash=true){
  if(!pageInfo[page])page='overview';state.activePage=page;
  const [name,eyebrow,title,subtitle]=pageInfo[page];
  $('#page-name').textContent=name;$('#page-eyebrow').textContent=eyebrow;$('#page-title').textContent=title;$('#page-subtitle').textContent=subtitle;
  $$('.page').forEach(el=>el.hidden=el.id!==`${page}-page`);
  $$('[data-page]').forEach(el=>{el.classList.toggle('active',el.dataset.page===page);if(el.dataset.page===page)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
  if(updateHash && location.hash !== `#${page}`)history.pushState(null,'',`#${page}`);
  window.scrollTo({top:0,behavior:'auto'});haptic();
}
document.addEventListener('click', event=>{
  const nav=event.target.closest('[data-page]');if(nav)navigate(nav.dataset.page);
  if(event.target.closest('[data-create]'))openComposer();
  if(event.target.closest('[data-help]'))$('#help').showModal();
  const close=event.target.closest('[data-close]');if(close)closeModal(close.dataset.close);
});
$('.brand').addEventListener('click',()=>navigate('overview'));
window.addEventListener('hashchange',()=>navigate(location.hash.slice(1),false));
navigate(location.hash.slice(1)||'overview',false);
// Header and sidebar help actions share the delegated handler above.
$('#dismiss-demo').addEventListener('click',()=>$('#demo-banner').hidden=true);
function closeModal(id){if(id==='composer'&&state.busy)return;document.getElementById(id).close();}
$$('dialog').forEach(dialog=>{dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal(dialog.id);}});dialog.addEventListener('cancel',e=>{if(dialog.id==='composer'&&state.busy)e.preventDefault();});});
let toastTimer;
function toast(message){clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').hidden=false;toastTimer=setTimeout(()=>$('#toast').hidden=true,6000);}
function dateLabel(value){if(!value)return 'Saved post';const d=new Date(value);return Number.isNaN(d.getTime())?'Saved post':d.toLocaleDateString('en-GB',{month:'short',day:'numeric'});}
function initials(name){return String(name||'You').split(/\s+/).filter(Boolean).slice(0,2).map(s=>s[0]).join('').toUpperCase();}
async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.method === 'POST' ? 60000 : 25000);
  try {
    const response = await fetch(path, { ...options, headers: { ...headers, ...options.headers }, signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Unable to complete the request (${response.status}). Please try again.`);
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error(options.method === 'POST'
      ? 'The request took too long. Check your Telegram chat before retrying; your preview may already have arrived.'
      : 'The connection is taking too long. Please try again.');
    if (error instanceof TypeError) throw new Error('You appear to be offline. Check your connection and try again.');
    throw error;
  } finally { clearTimeout(timeout); }
}
function emptyState(title,description,create=false){return `<div class="empty-state">${icon('layers')}<h3>${escapeHTML(title)}</h3><p>${escapeHTML(description)}</p>${create?'<button class="button primary" data-create>Create your first post '+icon('plus')+'</button>':''}</div>`;}
function showStatus(title,message,retry=false){$('#status-panel').hidden=false;$('#status-panel').innerHTML=`<h3>${escapeHTML(title)}</h3><p>${escapeHTML(message)}</p>${retry?'<button class="button secondary" id="retry-load">Try again</button>':''}`;$('#retry-load')?.addEventListener('click',()=>loadData(false));}
function renderProfile(){
  const user=state.profile;if(!user)return;
  const name=[user.first_name,user.last_name].filter(Boolean).join(' ')||'Creator';
  $$('.user-name').forEach(el=>el.textContent=name);
  $$('.user-handle').forEach(el=>el.textContent=user.username?`@${user.username}`:'Your personal creative space');
  $$('.user-avatar').forEach(el=>{if(!el.querySelector('img'))el.textContent=initials(name);});
  $('#total-posts').textContent=user.total_posts.toLocaleString();$('#profile-total').textContent=user.total_posts.toLocaleString();$('#nav-count').textContent=user.total_posts;$('#profile-id').textContent=user.id;
}
function postCard(post){
  const lines=post.text.split('\n').filter(Boolean);const title=lines[0]||'A little visual inspiration';
  const visual=post.has_photo?`<div class="post-visual"><img class="post-image" alt="Photo attached to your post" loading="lazy" data-photo="${escapeHTML(post.id)}"><span class="post-type">${icon('image')} Photo post</span></div>`:`<div class="post-visual text-art"><span class="post-type">${icon('text')} Text post</span><span class="quote-mark">“</span><p>${escapeHTML(title)}</p></div>`;
  return `<article class="post-card">${visual}<div class="post-body"><h3>${escapeHTML(title)}</h3><p class="post-excerpt">${escapeHTML(lines.slice(1).join(' ')||'An idea worth keeping. A story worth sharing.')}</p><div class="post-bottom"><span>${icon('calendar')}${escapeHTML(dateLabel(post.created_at))}</span><span class="saved-badge">${icon('check-circle')}In your library</span></div></div><button class="post-open" data-post="${escapeHTML(post.id)}" aria-label="Open post: ${escapeHTML(title.slice(0,80))}"></button></article>`;
}
function renderPosts(){
  $('#photo-count').textContent=state.posts.filter(p=>p.has_photo).length;
  $('#recent-count').textContent=Math.min(state.posts.length,4);
  $('#recent-posts').innerHTML=state.posts.length?state.posts.slice(0,4).map(postCard).join(''):emptyState('Your story starts here','A fresh space for your next idea. Create your first post and make it yours.',state.ready);
  renderLibrary();loadImages($('#recent-posts'));
}
function renderLibrary(){
  const query=$('#post-search').value.toLowerCase().trim();
  const posts=state.posts.filter(p=>(state.filter==='all'||(state.filter==='photo')===p.has_photo)&&`${p.text} ${p.button_names.join(' ')}`.toLowerCase().includes(query));
  posts.sort((a,b) => (new Date(b.created_at).getTime() - new Date(a.created_at).getTime()) * ($('#post-sort').value === 'oldest' ? -1 : 1));
  $('#result-count').textContent = `${posts.length} of ${state.posts.length} loaded`;
  $('#library-posts').innerHTML=posts.length?posts.map(postCard).join(''):emptyState(query||state.filter!=='all'?'No matching posts':'A blank page. Endless possibilities.',query||state.filter!=='all'?'Try a different filter or load more posts to keep exploring.':'Your next photo or thought could be the start of something good.',!query&&state.filter==='all'&&state.ready);
  $('#load-more').hidden=!state.hasMore;loadImages($('#library-posts'));
}
function renderLeaders(){
  $('#leaderboard').innerHTML=state.leaderboard.length?state.leaderboard.map((u,i)=>`<div class="leader-row"><span class="rank">${String(i+1).padStart(2,'0')}</span><span class="avatar small" style="background:${['#f0e6d7','#e9e2f5','#e0eee7'][i%3]}">${escapeHTML(initials(u.name))}</span><span class="leader-name">${escapeHTML(u.name)}</span><span class="leader-score">${Number(u.total_posts).toLocaleString()} posts</span></div>`).join(''):emptyState('Every community starts somewhere','Create a post and help this creative community grow.');
}
$$('[data-filter]').forEach(button=>button.addEventListener('click',()=>{state.filter=button.dataset.filter;$$('[data-filter]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',String(b===button));});renderLibrary();haptic();}));
$('#post-search').addEventListener('input',renderLibrary);
$('#load-more').addEventListener('click',()=>loadData(true));
$('#post-sort').addEventListener('change',renderLibrary);
$('#refresh-posts').addEventListener('click',async()=>{
  if(demo){renderPosts();toast('Demo library refreshed. These are sample posts.');return;}
  if(!initData){toast('Open your workspace in Telegram to load your posts.');return;}
  await loadData(false);
});
async function loadData(more=false){
  if(state.loading)return;
  state.loading=true;
  $('#refresh-posts').disabled=true;
  $('#load-more').disabled=true;
  $('#library-posts').setAttribute('aria-busy','true');
  if(!more){$('#status-panel').hidden=true;$('#recent-posts').innerHTML='<div class="skeleton"></div><div class="skeleton"></div>';}
  try{
    const data=await api(`/api/data?page=${more?state.page+1:0}`);
    state.profile=data.profile;state.leaderboard=data.leaderboard;state.page=data.page;state.hasMore=data.has_more;state.ready=true;
    state.posts=more?[...new Map([...state.posts,...data.posts].map(p=>[p.id,p])).values()]:data.posts;
    renderProfile();renderPosts();renderLeaders();
  }catch(error){if(!more){showStatus('Your studio will be right here.',error.message,true);if(!state.ready){$('#recent-posts').innerHTML=emptyState('Unable to load your library','Your posts have not been changed. Try again in a moment.');$('#library-posts').innerHTML=$('#recent-posts').innerHTML;}}else toast(error.message);}
  finally{state.loading=false;$('#load-more').disabled=false;$('#refresh-posts').disabled=false;$('#library-posts').setAttribute('aria-busy','false');}
}
async function mediaURL(path){
  if(state.photoCache.has(path))return state.photoCache.get(path);
  if(!state.mediaJobs.has(path))state.mediaJobs.set(path,(async()=>{
    const response=await fetch(path,{headers,signal:AbortSignal.timeout(20000)});
    if(!response.ok||response.status===204)return null;
    if(!response.headers.get('content-type')?.startsWith('image/'))return null;
    const url=URL.createObjectURL(await response.blob());state.photoCache.set(path,url);return url;
  })().finally(()=>state.mediaJobs.delete(path)));
  return state.mediaJobs.get(path);
}
async function attachImage(image){
  const post=state.posts.find(p=>p.id===image.dataset.photo);if(!post)return;
  try{
    const url=demo?post.demo_image:await mediaURL(`/api/posts/${encodeURIComponent(post.id)}/photo`);
    if(!url)throw new Error('Unavailable');
    image.onerror=()=>{image.replaceWith(Object.assign(document.createElement('div'),{className:'media-unavailable',textContent:'Photo preview unavailable'}));};
    image.src=url;
  }catch(_){image.replaceWith(Object.assign(document.createElement('div'),{className:'media-unavailable',textContent:'Photo preview unavailable'}));}
}
const photoObserver='IntersectionObserver' in window?new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){photoObserver.unobserve(entry.target);attachImage(entry.target);}}),{rootMargin:'120px'}):null;
function loadImages(root){$$('[data-photo]',root).forEach(image=>photoObserver?photoObserver.observe(image):attachImage(image));}
async function loadAvatar(){try{const url=await mediaURL('/api/profile/photo');if(url)$$('.user-avatar').forEach(el=>{const image=new Image();image.alt='';image.src=url;el.append(image);});}catch(_){/* Initials remain a useful, accessible fallback. */}}
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-post]');if(!button)return;
  const post=state.posts.find(p=>p.id===button.dataset.post);if(!post)return;
  state.selectedPost=post;
  $('#detail-content').innerHTML=`<div class="detail-meta">${escapeHTML(dateLabel(post.created_at))} · Saved to your private library</div>${post.has_photo?`<img class="detail-photo" data-photo="${escapeHTML(post.id)}" alt="Your post photo">`:''}<p class="detail-text">${escapeHTML(post.text)}</p>${post.button_names.map(name=>`<div class="detail-button">${escapeHTML(name)}</div>`).join('')}<div class="privacy-hint">${icon('lock')} ${post.button_names.length?'Button labels only. Destinations are private and never sent to this page.':'This post is only visible to you.'}</div>`;
  $('#detail').showModal();loadImages($('#detail-content'));haptic();
});
function openComposer(){
  if(!initData&&!demo){toast('Open your profile from the Telegram bot to create a post.');return;}
  $('#compose-error').hidden=true;updatePreview();$('#composer').showModal();haptic();
}
function countText(){const hasPhoto=Boolean($('#photo-input').files.length);const limit=hasPhoto?1024:4096;$('#post-text').maxLength=limit;$('#char-count').textContent=`${$('#post-text').value.length.toLocaleString()} / ${limit.toLocaleString()}`;$('#char-count').classList.toggle('over-limit',$('#post-text').value.length>limit);updatePreview();}
$('#post-text').addEventListener('input',countText);
function clearPhoto(){if(state.photoURL)URL.revokeObjectURL(state.photoURL);state.photoURL=null;$('#photo-input').value='';$('#selected-photo').removeAttribute('src');$('#photo-preview').hidden=true;$('#upload-zone').hidden=false;countText();}
$('#photo-input').addEventListener('change',()=>{
  const file=$('#photo-input').files[0];if(!file){clearPhoto();return;}
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>9*1024*1024){clearPhoto();showComposeError('Choose a JPEG, PNG or WebP photo smaller than 9 MB.');return;}
  if(state.photoURL)URL.revokeObjectURL(state.photoURL);state.photoURL=URL.createObjectURL(file);$('#selected-photo').src=state.photoURL;$('#photo-preview').hidden=false;$('#upload-zone').hidden=true;countText();
});
$('#remove-photo').addEventListener('click',clearPhoto);
$('#add-button').addEventListener('click',()=>{
  if($$('.button-row').length>=10)return;
  const row=document.createElement('div');row.className='button-row';
  row.innerHTML=`<input aria-label="Button label" placeholder="Button label" maxlength="64" required><input aria-label="Button destination" placeholder="https:// or @username" maxlength="2048" required><button class="icon-button" type="button" aria-label="Remove button">${icon('close')}</button>`;
  $('button',row).addEventListener('click',()=>{row.remove();$('#add-button').disabled=false;updatePreview();});$('#button-fields').append(row);$('input',row).focus();$('#add-button').disabled=$$('.button-row').length>=10;
});
function showComposeError(message){$('#compose-error').textContent=message;$('#compose-error').hidden=false;$('#compose-error').scrollIntoView({block:'nearest'});}
$('#compose-form').addEventListener('submit',async event=>{
  event.preventDefault();if(state.busy)return;
  const text=$('#post-text').value.trim();const photo=$('#photo-input').files[0];
  if(!text&&!photo){showComposeError('Write a little something, or add a photo to get started.');return;}
  if(text.length>(photo?1024:4096)){showComposeError(photo?'Photo captions can be up to 1,024 characters.':'Keep your post under 4,096 characters.');return;}
  if(demo){showComposeError('This is a design preview—nothing has been sent. Open the live mini app from your Telegram bot to create a real post.');return;}
  const buttons=$$('.button-row').map(row=>({name:$$('input',row)[0].value.trim(),url:$$('input',row)[1].value.trim()}));
  const data=new FormData();data.append('text',text);data.append('buttons',JSON.stringify(buttons));if(photo)data.append('photo',photo);
  state.busy=true;$('#compose-error').hidden=true;$('#submit-post').disabled=true;$('#submit-post').textContent='Creating your preview…';
  try{
    state.submissionKey ||= crypto.randomUUID();
    const result=await api('/api/compose',{method:'POST',body:data,headers:{'X-Idempotency-Key':state.submissionKey}});
    state.submissionKey=null;
    state.busy=false;$('#composer').close();$('#compose-form').reset();clearPhoto();$('#button-fields').replaceChildren();$('#add-button').disabled=false;
    toast(result.warning||'Preview sent! Return to your Telegram bot to choose where to publish.');
    await loadData(false);
  }catch(error){showComposeError(error.message);}
  finally{state.busy=false;$('#submit-post').disabled=false;$('#submit-post').innerHTML='Send preview to Telegram '+icon('send');}
});
function loadDemo(){
  $('#demo-banner').hidden=false;$('#connection').innerHTML='<span class="status-dot"></span> Design preview';
  state.profile={id:123456789,first_name:'Alex',last_name:'Morgan',username:'alexcreates',total_posts:4};
  const now=Date.now();
  state.posts=[
    {id:'sample-1',text:'A fresh perspective.\nSometimes all you need is a little distance to see things differently. Here’s to finding inspiration in the everyday.',has_photo:true,demo_image:'https://sspark.genspark.ai/i/liPaEjkeyWnhSN7L?width=2560',button_names:['Explore more'],created_at:new Date(now-3600000).toISOString()},
    {id:'sample-2',text:'Small steps.\nBeautiful things.\nA reminder to keep showing up, even on the quiet days. Progress doesn’t always need to be loud.',has_photo:false,button_names:[],created_at:new Date(now-86400000).toISOString()},
    {id:'sample-3',text:'Chasing the golden hour.\nA moment of stillness before the world wakes up. Save a little space for the things that make you pause.',has_photo:true,demo_image:'https://sspark.genspark.ai/i/bayWHPFQZlmtDZhb?width=2560',button_names:['See the story'],created_at:new Date(now-172800000).toISOString()},
    {id:'sample-4',text:'Your next chapter starts now.\nA blank page isn’t empty. It’s full of possibilities. What will you make today?',has_photo:false,button_names:['Join the conversation'],created_at:new Date(now-259200000).toISOString()}
  ];
  state.leaderboard=[{name:'Maya Chen',total_posts:38},{name:'Arjun Patel',total_posts:32},{name:'Sofia Rivera',total_posts:27},{name:'Jamie Park',total_posts:19},{name:'Alex Morgan',total_posts:4}];state.ready=true;
  renderProfile();renderPosts();renderLeaders();
}
if(demo)loadDemo();else if(initData){loadData();loadAvatar();}else{showStatus('Your private studio lives in Telegram.','Open “My profile” from your bot to securely see your own profile and posts.');$('#recent-posts').innerHTML=emptyState('A space that’s just for you','Your library will appear after you open this mini app from Telegram.');$('#library-posts').innerHTML=$('#recent-posts').innerHTML;$('#leaderboard').innerHTML=emptyState('Meet your community in Telegram','Open the mini app from your bot to see the creator leaderboard.');}
window.addEventListener('pagehide',()=>{for(const url of state.photoCache.values())URL.revokeObjectURL(url);state.photoCache.clear();});
