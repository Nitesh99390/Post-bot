'use strict';
// Inline SVGs avoid icon-library downloads and remain crisp at any display scale.
const icons = {
  monitor: '<rect x="3" y="3" width="18" height="13" rx="2"/><path d="M8 21h8M12 16v5"/>',
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
const state = {posts:[], profile:null, leaderboard:[], page:0, hasMore:false, filter:'all', activePage:'overview', busy:false, photoURL:null, photoCache:new Map(), mediaJobs:new Map(), ready:false, loading:false, selectedPost:null, submissionKey:null, sending:false};
const headers = {'X-Telegram-Init-Data': initData};
try{tg?.ready();tg?.expand();if(tg?.isVersionAtLeast?.('6.1')){tg.setHeaderColor('#f8f9fc');tg.setBackgroundColor('#f8f9fc');}}catch(_){/* Older Telegram clients use safe defaults. */}
try{if(initData&&tg?.isVersionAtLeast?.('8.0'))tg.requestFullscreen?.();}catch(_){/* Expanded mode remains available on unsupported clients. */}
function haptic(){try{if(tg?.isVersionAtLeast?.('6.1'))tg.HapticFeedback?.selectionChanged();}catch(_){}}
const pageInfo = {
  overview:['Your studio','Create. Save. Share.'],
  posts:['Saved posts','Keep it here. Send it later.'],
  community:['Global rank','The creators who keep creating.'],
  profile:['Profile','Your Telegram account.']
};
function navigate(page, updateHash=true){
  if(!pageInfo[page])page='overview';state.activePage=page;
  const [title,subtitle]=pageInfo[page];
  $('#page-title').textContent=title;$('#page-subtitle').textContent=subtitle;
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
function closeModal(id){if((id==='composer'&&state.busy)||(id==='detail'&&state.sending))return;document.getElementById(id).close();}
$$('dialog').forEach(dialog=>{dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal(dialog.id);}});dialog.addEventListener('cancel',e=>{if((dialog.id==='composer'&&state.busy)||(dialog.id==='detail'&&state.sending))e.preventDefault();});});
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
  $$('.user-handle').forEach(el=>el.textContent=user.username?`@${user.username}`:'Telegram creator');
  $$('.user-avatar').forEach(el=>{if(!el.querySelector('img'))el.textContent=initials(name);});
  $('#total-posts').textContent=user.total_posts.toLocaleString();$('#profile-total').textContent=user.total_posts.toLocaleString();$('#nav-count').textContent=user.total_posts;$('#profile-id').textContent=user.id;
}
function postCard(post){
  const lines=post.text.split('\n').filter(Boolean);const title=lines[0]||'Photo post';
  const visual=post.has_photo?`<div class="post-visual"><img class="post-image" alt="Photo attached to your post" loading="lazy" data-photo="${escapeHTML(post.id)}"><span class="post-type">${icon('image')} Photo post</span></div>`:`<div class="post-visual text-art"><span class="post-type">${icon('text')} Text post</span><span class="quote-mark">“</span><p>${escapeHTML(title)}</p></div>`;
  return `<article class="post-card">${visual}<div class="post-body"><h3>${escapeHTML(title)}</h3><div class="post-bottom"><span>${icon('calendar')}${escapeHTML(dateLabel(post.created_at))}</span><span class="saved-badge">${icon('check-circle')}Saved</span></div></div><button class="post-open" data-post="${escapeHTML(post.id)}" aria-label="Open post: ${escapeHTML(title.slice(0,80))}"></button></article>`;
}
function renderPosts(){
  $('#recent-count').textContent=Math.min(state.posts.length,2);
  $('#recent-posts').innerHTML=state.posts.length?state.posts.slice(0,2).map(postCard).join(''):emptyState('No saved posts yet','Create your first post.',state.ready);
  renderLibrary();loadImages($('#recent-posts'));
}
function renderLibrary(){
  const query=$('#post-search').value.toLowerCase().trim();
  const posts=state.posts.filter(p=>(state.filter==='all'||(state.filter==='photo')===p.has_photo)&&`${p.text} ${p.button_names.join(' ')}`.toLowerCase().includes(query));
  posts.sort((a,b) => (new Date(b.created_at).getTime() - new Date(a.created_at).getTime()) * ($('#post-sort').value === 'oldest' ? -1 : 1));
  $('#result-count').textContent = `${posts.length} of ${state.posts.length} loaded`;
  $('#library-posts').innerHTML=posts.length?posts.map(postCard).join(''):emptyState(query||state.filter!=='all'?'No matching posts':'No saved posts yet',query||state.filter!=='all'?'Try another filter or load more posts.':'Tap New post to get started.',!query&&state.filter==='all'&&state.ready);
  $('#load-more').hidden=!state.hasMore;loadImages($('#library-posts'));
}
function renderLeaders(){
  const own = state.leaderboard.findIndex(user => user.is_you);
  $('#profile-rank').textContent=own>=0?`#${own+1}`:'Not in top 100';
  $('#my-rank').hidden=!state.profile;
  $('#my-rank').innerHTML=`<span>Your rank</span><strong>${own>=0?`#${own+1}`:'Not in top 100 yet'}</strong>`;
  $('#leaderboard').innerHTML=state.leaderboard.length?state.leaderboard.map((u,i)=>`<div class="leader-row${u.is_you?' is-you':''}"><span class="rank">${String(i+1).padStart(2,'0')}</span><span class="avatar small" style="background:${['#f0e6d7','#e9e2f5','#e0eee7'][i%3]}">${escapeHTML(initials(u.name))}</span><span class="leader-name">${escapeHTML(u.name)}${u.is_you?' · You':''}</span><span class="leader-score">${Number(u.total_posts).toLocaleString()}</span></div>`).join(''):emptyState('Be the first creator','Save a post to join the ranking.');
}
$$('[data-filter]').forEach(button=>button.addEventListener('click',()=>{state.filter=button.dataset.filter;$$('[data-filter]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',String(b===button));});renderLibrary();haptic();}));
$('#post-search').addEventListener('input',renderLibrary);
$('#load-more').addEventListener('click',()=>loadData(true));
$('#post-sort').addEventListener('change',renderLibrary);
$('#refresh-posts').addEventListener('click',async()=>{
  if(demo){renderPosts();toast('Sample posts refreshed.');return;}
  if(!initData){toast('Open the mini app in Telegram.');return;}
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
  }catch(error){if(!more){showStatus('Could not load posts',error.message,true);if(!state.ready){$('#recent-posts').innerHTML=emptyState('Unable to load your library','Your posts have not been changed. Try again in a moment.');$('#library-posts').innerHTML=$('#recent-posts').innerHTML;}}else toast(error.message);}
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
async function loadAvatar(){try{const url=await mediaURL('/api/profile/photo');if(url)$$('.user-avatar').forEach(el=>{const image=new Image();image.alt='Your Telegram profile photo';image.src=url;image.onerror=()=>image.remove();el.append(image);});}catch(_){/* Fall back to initials. */}}
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-post]');if(!button)return;
  const post=state.posts.find(p=>p.id===button.dataset.post);if(!post)return;
  state.selectedPost=post;
  $('#send-options').open=false;$('#send-error').hidden=true;$('#send-status').textContent='';$('#send-form').reset();$('#copy-post').innerHTML=icon('copy')+' Copy text';
  $('#detail-content').innerHTML=`<div class="detail-meta">${escapeHTML(dateLabel(post.created_at))} · Saved</div>${post.has_photo?`<img class="detail-photo" data-photo="${escapeHTML(post.id)}" alt="Your post photo">`:''}<p class="detail-text">${escapeHTML(post.text)}</p>${post.button_names.map(name=>`<div class="detail-button">${escapeHTML(name)}</div>`).join('')}`;
  $('#detail').showModal();loadImages($('#detail-content'));haptic();
});
$('#show-send').addEventListener('click',()=>{
  $('#send-options').open=true;$('#send-options').scrollIntoView({block:'nearest',behavior:'smooth'});$('#share-post').focus();
});
async function sendSaved(action,target){
  if(!state.selectedPost||state.sending)return;
  $('#send-error').hidden=true;$('#send-status').textContent='';
  if(demo){$('#send-error').textContent='Demo only. Open the live Telegram mini app to send saved posts.';$('#send-error').hidden=false;return;}
  if(action==='share'&&(!tg?.isVersionAtLeast?.('8.0')||typeof tg.shareMessage!=='function')){
    $('#send-error').textContent='Update Telegram to choose a chat here. Or use Send to my bot, then forward the post.';$('#send-error').hidden=false;return;
  }
  state.sending=true;
  $$('#send-options button, #send-options input, #show-send').forEach(el=>el.disabled=true);
  $('#send-status').textContent=action==='share'?'Preparing your post…':'Sending…';
  try{
    const result=await api(`/api/posts/${encodeURIComponent(state.selectedPost.id)}/send`,{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,target})
    });
    if(action==='share'){
      $('#send-status').textContent='Choose a chat in Telegram.';
      tg.shareMessage(result.prepared_id,sent=>{$('#send-status').textContent=sent?'Post shared.':'Not shared. You can try again.';});
    }else $('#send-status').textContent=action==='self'?'Sent to your bot. You can forward it from there.':'Post sent to your channel.';
  }catch(error){$('#send-status').textContent='';$('#send-error').textContent=error.message;$('#send-error').hidden=false;}
  finally{state.sending=false;$$('#send-options button, #send-options input, #show-send').forEach(el=>el.disabled=false);}
}
$('#share-post').addEventListener('click',()=>sendSaved('share'));
$('#send-self').addEventListener('click',()=>sendSaved('self'));
$('#send-form').addEventListener('submit',event=>{event.preventDefault();sendSaved('publish',$('#send-target').value.trim());});
function openComposer(){
  if(!initData&&!demo){toast('Open this mini app from your Telegram bot.');return;}
  $('#compose-error').hidden=true;updatePreview();$('#composer').showModal();haptic();
}
function countText(){const hasPhoto=Boolean($('#photo-input').files.length);const limit=hasPhoto?1024:4096;$('#post-text').maxLength=limit;$('#char-count').textContent=`${$('#post-text').value.length.toLocaleString()} / ${limit.toLocaleString()}`;$('#char-count').classList.toggle('over-limit',$('#post-text').value.length>limit);updatePreview();}
$('#post-text').addEventListener('input',countText);
function clearPhoto(){state.submissionKey=null;if(state.photoURL)URL.revokeObjectURL(state.photoURL);state.photoURL=null;$('#photo-input').value='';$('#selected-photo').removeAttribute('src');$('#photo-preview').hidden=true;$('#upload-zone').hidden=false;countText();}
$('#photo-input').addEventListener('change',()=>{
  const file=$('#photo-input').files[0];if(!file){clearPhoto();return;}
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>9*1024*1024){clearPhoto();showComposeError('Choose a JPEG, PNG or WebP photo smaller than 9 MB.');return;}
  if(state.photoURL)URL.revokeObjectURL(state.photoURL);state.photoURL=URL.createObjectURL(file);$('#selected-photo').src=state.photoURL;$('#photo-preview').hidden=false;$('#upload-zone').hidden=true;countText();
});
$('#remove-photo').addEventListener('click',clearPhoto);
$('#add-button').addEventListener('click',()=>{
  if(state.busy||$$('.button-row').length>=10)return;
  const row=document.createElement('div');row.className='button-row';
  row.innerHTML=`<input aria-label="Button label" placeholder="Button label" maxlength="64" required><input aria-label="Button destination" placeholder="https:// or @username" maxlength="2048" required><button class="icon-button" type="button" aria-label="Remove button">${icon('close')}</button>`;
  $('button',row).addEventListener('click',()=>{row.remove();$('#add-button').disabled=false;state.submissionKey=null;updatePreview();});$('#button-fields').append(row);$('input',row).focus();$('#add-button').disabled=$$('.button-row').length>=10;
});
function showComposeError(message){$('#compose-error').textContent=message;$('#compose-error').hidden=false;$('#compose-error').scrollIntoView({block:'nearest'});}
function setComposerBusy(busy){
  $$('#compose-form input, #compose-form textarea, #compose-form button').forEach(el=>el.disabled=busy);
  if(!busy)$('#add-button').disabled=$$('.button-row').length>=10;
}
$('#compose-form').addEventListener('invalid',event=>{
  let parent=event.target.parentElement;
  while(parent){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement;}
},true);
$('#compose-form').addEventListener('submit',async event=>{
  event.preventDefault();if(state.busy)return;
  const text=$('#post-text').value.trim();const photo=$('#photo-input').files[0];
  if(!text&&!photo){showComposeError('Write a post or add a photo.');return;}
  if(text.length>(photo?1024:4096)){showComposeError(photo?'Photo captions can be up to 1,024 characters.':'Keep your post under 4,096 characters.');return;}
  if(demo){showComposeError('This is a design preview—nothing has been sent. Open the live mini app from your Telegram bot to create a real post.');return;}
  const buttons=$$('.button-row').map(row=>({name:$$('input',row)[0].value.trim(),url:$$('input',row)[1].value.trim()}));
  const data=new FormData();data.append('save_only','1');data.append('text',text);data.append('buttons',JSON.stringify(buttons));if(photo)data.append('photo',photo);
  state.busy=true;$('#compose-error').hidden=true;setComposerBusy(true);$('#submit-post').textContent='Saving…';
  try{
    state.submissionKey ||= crypto.randomUUID();
    const result=await api('/api/compose',{method:'POST',body:data,headers:{'X-Idempotency-Key':state.submissionKey}});
    state.submissionKey=null;
    state.busy=false;$('#composer').close();$('#compose-form').reset();clearPhoto();$('#button-fields').replaceChildren();$('#add-button').disabled=false;
    toast(result.saved?'Post saved. Share it anytime.':result.warning||'Your preview is in Telegram.');
    $$('#compose-form details').forEach(el=>el.open=false);
    navigate('posts');await loadData(false);
  }catch(error){showComposeError(error.message);}
  finally{state.busy=false;setComposerBusy(false);$('#submit-post').innerHTML='Save post '+icon('check');}
});
// Build preview nodes with a strict formatting allowlist; never inject user HTML.
function updatePreview() {
  const root = $('#live-text');
  root.replaceChildren();
  const text = $('#post-text').value;
  if (!text.trim()) {
    const placeholder = document.createElement('span');
    placeholder.className = 'preview-placeholder';
    placeholder.textContent = 'Your post preview…';
    root.append(placeholder);
  } else {
    const parsed = new DOMParser().parseFromString(text, 'text/html');
    const allowed = new Set(['B', 'STRONG', 'I', 'EM', 'U', 'S', 'DEL', 'CODE', 'PRE', 'BLOCKQUOTE']);
    function appendSafe(source, target, depth = 0) {
      if (depth > 40) { target.append(document.createTextNode(source.textContent)); return; }
      for (const node of source.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) target.append(document.createTextNode(node.textContent));
        else if (node.nodeType === Node.ELEMENT_NODE) {
          if (node.tagName === 'BR') { target.append(document.createElement('br')); continue; }
          if (allowed.has(node.tagName)) {
            const element = document.createElement(node.tagName.toLowerCase());
            appendSafe(node, element, depth + 1);
            target.append(element);
          } else appendSafe(node, target, depth + 1);
        }
      }
    }
    appendSafe(parsed.body, root);
  }
  $('#live-photo').hidden = !state.photoURL;
  if (state.photoURL) $('#live-photo').src = state.photoURL;
  else $('#live-photo').removeAttribute('src');
  $('#live-buttons').replaceChildren();
  $$('.button-row').forEach(row => {
    const label = document.createElement('div');
    label.textContent = $('input', row).value.trim() || 'Your button label';
    $('#live-buttons').append(label);
  });
}

// Preferences are the only data persisted in the browser. Drafts and links are not.
// Change only the layout: never reload, rewrite Telegram initData, or save drafts.
const layoutStorageKey = 'poststudio-layout';
function setLayout(mode, persist = false) {
  const desktop = mode === 'desktop';
  document.documentElement.dataset.layout = desktop ? 'desktop' : 'auto';
  $$('[data-layout-toggle]').forEach(button => {
    button.setAttribute('aria-pressed', String(desktop));
    button.title = desktop ? 'Turn off desktop mode' : 'Open the wide desktop layout';
  });
  $$('[data-layout-state]').forEach(label => { label.textContent = desktop ? 'On' : 'Off'; });
  $('[data-layout-caption]').textContent = desktop ? 'Desktop layout' : 'Auto layout';
  $('[data-desktop-hint]').hidden = !desktop;
  if (persist) {
    try { localStorage.setItem(layoutStorageKey, desktop ? 'desktop' : 'auto'); }
    catch (_) { /* The switch still works when storage is unavailable. */ }
  }
  // Bring content into view; the fixed toolbar stays reachable while panning.
  window.scrollTo({ left: 0, top: window.scrollY, behavior: 'instant' });
}
let savedLayout;
try { savedLayout = localStorage.getItem(layoutStorageKey); } catch (_) { /* Default to auto. */ }
setLayout(savedLayout);
$$('[data-layout-toggle]').forEach(button => button.addEventListener('click', () => {
  const desktop = document.documentElement.dataset.layout !== 'desktop';
  setLayout(desktop ? 'desktop' : 'auto', true);
  haptic();
  toast(desktop ? 'Desktop mode on. On smaller screens, swipe sideways to explore.' : 'Desktop mode off. Layout now fits your screen automatically.');
}));

function setTheme(theme) {
  const dark = theme === 'dark';
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  $('#theme-toggle').innerHTML = icon(dark ? 'sun' : 'moon');
  $('#theme-toggle').setAttribute('aria-label', `Switch to ${dark ? 'light' : 'dark'} mode`);
  $('meta[name="theme-color"]').content = dark ? '#15151e' : '#f8f9fc';
  try { localStorage.setItem('poststudio-theme', theme); } catch (_) { /* Private browsing may block storage. */ }
  try { if(tg?.isVersionAtLeast?.('6.1')) { tg.setHeaderColor(dark ? '#15151e' : '#f8f9fc'); tg.setBackgroundColor(dark ? '#15151e' : '#f8f9fc'); } } catch (_) { /* Older clients retain their theme. */ }
}
let savedTheme;
try { savedTheme = localStorage.getItem('poststudio-theme'); } catch (_) { /* Use the system default. */ }
setTheme(savedTheme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
$('#theme-toggle').addEventListener('click', () => {
  setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  haptic();
});

$('#compose-form').addEventListener('input', () => { state.submissionKey = null; updatePreview(); });
$('#compose-form').addEventListener('change', () => { state.submissionKey = null; });
$$('[data-format]').forEach(button => button.addEventListener('click', () => {
  const input = $('#post-text');
  const { selectionStart: start, selectionEnd: end } = input;
  const tag = button.dataset.format;
  const selection = input.value.slice(start, end) || 'your text';
  const replacement = `<${tag}>${selection}</${tag}>`;
  if (input.value.length - (end - start) + replacement.length > input.maxLength) {
    showComposeError('There is not enough space to add formatting. Shorten your message first.');
    return;
  }
  input.setRangeText(replacement, start, end, 'select');
  input.focus();
  input.dispatchEvent(new Event('input', { bubbles: true }));
  countText();
}));

// Support drag-and-drop without allowing the browser to navigate to a local file.
const uploadZone = $('#upload-zone');
['dragenter', 'dragover'].forEach(name => uploadZone.addEventListener(name, event => {
  event.preventDefault();
  uploadZone.classList.add('dragging');
}));
['dragleave', 'drop'].forEach(name => uploadZone.addEventListener(name, event => {
  event.preventDefault();
  uploadZone.classList.remove('dragging');
}));
uploadZone.addEventListener('drop', event => {
  if (state.busy) return;
  const file = event.dataTransfer.files[0];
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  $('#photo-input').files = transfer.files;
  $('#photo-input').dispatchEvent(new Event('change', { bubbles: true }));
});

$('#copy-post').addEventListener('click', async () => {
  if (!state.selectedPost) return;
  const button = $('#copy-post');
  try {
    await navigator.clipboard.writeText(state.selectedPost.text);
    button.innerHTML = icon('check') + ' Copied!';
    setTimeout(() => { button.innerHTML = icon('copy') + ' Copy text'; }, 2000);
  } catch (_) {
    button.textContent = 'Select the text above to copy it';
  }
});

document.addEventListener('keydown', event => {
  if (event.ctrlKey || event.metaKey || event.altKey || event.repeat || event.isComposing) return;
  if (event.target.closest('input, textarea, select, [contenteditable="true"]') || $('dialog[open]')) return;
  if (event.key.toLowerCase() === 'n') { event.preventDefault(); openComposer(); }
  if (event.key === '/') { event.preventDefault(); navigate('posts'); $('.library-options').open=true; $('#post-search').focus(); }
});
window.addEventListener('beforeunload', event => {
  if ($('#post-text').value.trim() || $('#photo-input').files.length || state.busy) {
    event.preventDefault();
    event.returnValue = '';
  }
});
window.addEventListener('offline', () => toast('You’re offline. Your current draft is still here.'));
window.addEventListener('online', () => toast('You’re back online. Ready when you are.'));

function loadDemo(){
  $('#demo-banner').hidden=false;
  state.profile={id:123456789,first_name:'Alex',last_name:'Morgan',username:'alexcreates',total_posts:4};
  const now=Date.now();
  state.posts=[
    {id:'sample-1',text:'A fresh perspective.\nSometimes all you need is a little distance to see things differently. Here’s to finding inspiration in the everyday.',has_photo:true,demo_image:'/static/demo-mountains.webp',button_names:['Explore more'],created_at:new Date(now-3600000).toISOString()},
    {id:'sample-2',text:'Small steps.\nBeautiful things.\nA reminder to keep showing up, even on the quiet days. Progress doesn’t always need to be loud.',has_photo:false,button_names:[],created_at:new Date(now-86400000).toISOString()},
    {id:'sample-3',text:'Chasing the golden hour.\nA moment of stillness before the world wakes up. Save a little space for the things that make you pause.',has_photo:true,demo_image:'/static/demo-ocean.webp',button_names:['See the story'],created_at:new Date(now-172800000).toISOString()},
    {id:'sample-4',text:'Your next chapter starts now.\nA blank page isn’t empty. It’s full of possibilities. What will you make today?',has_photo:false,button_names:['Join the conversation'],created_at:new Date(now-259200000).toISOString()}
  ];
  state.leaderboard=Array.from({length:100},(_,i)=>({name:['Maya Chen','Arjun Patel','Sofia Rivera','Jamie Park'][i]||`Sample creator ${i+1}`,total_posts:400-i*4,is_you:i===99}));
  state.leaderboard[99].name='Alex Morgan';state.ready=true;
  renderProfile();renderPosts();renderLeaders();
}
if(demo)loadDemo();else if(initData){loadData();loadAvatar();}else{showStatus('Open in Telegram','Launch the mini app from your bot to see your posts.');$('#recent-posts').innerHTML=emptyState('Your saved posts','Sign in through Telegram to continue.');$('#library-posts').innerHTML=$('#recent-posts').innerHTML;$('#leaderboard').innerHTML=emptyState('Meet your community in Telegram','Open the mini app from your bot to see the creator leaderboard.');}
window.addEventListener('pagehide',()=>{for(const url of state.photoCache.values())URL.revokeObjectURL(url);state.photoCache.clear();});
