<script>
let currentSection=1,currentQuestion=1,timeInSeconds=1800,timerInterval=null,timerRunning=false,savedRange=null,activeHLMark=null,checked=false,currentPlaybackRate=1,transcriptReviewMode=false,transcriptPanelOpen=false,currentTextSize='medium',currentAudio=null,armedListeningMatch=null;
const listeningMatchAssignments={};
const correctAnswers={
  '1':['7.45','7:45','7 45','745'],'2':'celebration','3':'vegetarian','4':['strawberries','strawberry'],'5':'cheese',
  '6':'disco','7':['flowers','flower'],'8':'congratulations','9':'taxi','10':['07749132760','07749 132760','07749-132760'],
  '11':'B','12':'A','13':'C','14':'B','15':'C','16':'D','17':'F','18':'B','19':'G','20':'A',
  '21':'B','22':'C','23':'C','24':'B','25':'A','26':'D','27':'F','28':'G','29':'B','30':'E',
  '31':'bear','32':'source','33':'bread','34':['oranges','orange'],'35':'clean','36':['emotions','emotion'],
  '37':'gym','38':'threat','39':'chocolate','40':['spices','spice']
};
const pickTwoGroups=[];
const pickQuestionIds=new Set(pickTwoGroups.flatMap(g=>g.questionIds));
const questionResultStates={};

function sectionForQuestion(n){return n<=10?1:n<=20?2:n<=30?3:4}
function formatTime(seconds){if(!Number.isFinite(seconds))return '0:00';seconds=Math.max(0,Math.floor(seconds));return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`}
function initialize(){
  document.querySelectorAll('.section-tab').forEach(btn=>btn.addEventListener('click',()=>switchToSection(Number(btn.dataset.section))));
  document.querySelectorAll('.answer-input').forEach(el=>{el.addEventListener('input',()=>{currentQuestion=Number(el.dataset.question);updateAllIndicators()});el.addEventListener('focus',()=>{currentQuestion=Number(el.dataset.question);updateAllIndicators()})});
  document.querySelectorAll('input[type="radio"]').forEach(el=>el.addEventListener('change',()=>{const n=Number(el.name.replace('q',''));currentQuestion=n;syncMapCells();updateAllIndicators()}));
  document.querySelectorAll('.lmap-cell').forEach(cell=>cell.addEventListener('click',()=>{if(checked)return;const input=cell.querySelector('input');input.checked=true;input.dispatchEvent(new Event('change',{bubbles:true}))}));
  document.querySelectorAll('.pick-two input').forEach(el=>el.addEventListener('change',handlePickTwoChange));
  document.getElementById('audioPlay').addEventListener('click',toggleAudio);
  document.getElementById('back10').addEventListener('click',()=>seekBy(-10));document.getElementById('forward10').addEventListener('click',()=>seekBy(10));
  document.getElementById('seekSlider').addEventListener('input',e=>{if(currentAudio&&Number.isFinite(currentAudio.duration))currentAudio.currentTime=(Number(e.target.value)/1000)*currentAudio.duration});
  document.getElementById('volumeSlider').addEventListener('input',e=>document.querySelectorAll('audio').forEach(a=>a.volume=Number(e.target.value)));
  document.getElementById('timerToggle').addEventListener('click',toggleTimer);document.getElementById('timerReset').addEventListener('click',resetTimer);document.getElementById('themeToggle').addEventListener('click',toggleTheme);document.getElementById('checkButton').addEventListener('click',()=>checked?showResultsModal():checkAnswers());
  document.querySelectorAll('.text-size-control [data-text-size]').forEach(btn=>btn.addEventListener('click',()=>setTextSize(btn.dataset.textSize)));
  document.getElementById('fullscreenBtn')?.addEventListener('click',toggleFullscreen);document.addEventListener('fullscreenchange',syncFullscreenButton);
  document.getElementById('closeTranscriptBtn')?.addEventListener('click',closeTranscriptPanel);document.getElementById('openTranscriptBtn')?.addEventListener('click',openTranscriptPanel);
  bindSpeedControl();bindAudio(document.getElementById('mainAudio'));initQuestionNav();initListeningDragMatching();initHighlighting();setTextSize('medium');syncFullscreenButton();switchToSection(1);resetTimer();updateAllIndicators();
}
function bindSpeedControl(){document.getElementById('speedControl').addEventListener('change',e=>{currentPlaybackRate=parseFloat(e.target.value)||1;applyPlaybackRateToCurrentAudio()})}
function applyPlaybackRateToCurrentAudio(){if(currentAudio)currentAudio.playbackRate=currentPlaybackRate}
function bindAudio(audio){
  currentAudio=audio;currentAudio.volume=Number(document.getElementById('volumeSlider').value);applyPlaybackRateToCurrentAudio();
  currentAudio.onloadedmetadata=updateAudioDisplay;currentAudio.ontimeupdate=updateAudioDisplay;currentAudio.onplay=()=>document.getElementById('audioPlay').textContent='❚❚';currentAudio.onpause=()=>document.getElementById('audioPlay').textContent='▶';currentAudio.onended=()=>document.getElementById('audioPlay').textContent='▶';updateAudioDisplay();
}
function updateAudioDisplay(){if(!currentAudio)return;const d=currentAudio.duration||0,c=currentAudio.currentTime||0;document.getElementById('seekSlider').value=d?Math.round(c/d*1000):0;document.getElementById('audioTime').textContent=`${formatTime(c)} / ${formatTime(d)}`}
function toggleAudio(){if(!currentAudio)return;if(currentAudio.paused)currentAudio.play().catch(()=>{});else currentAudio.pause()}
function seekBy(s){if(currentAudio)currentAudio.currentTime=Math.min(currentAudio.duration||Infinity,Math.max(0,currentAudio.currentTime+s))}
function switchToSection(n){
  if(n<1||n>4)return;currentSection=n;
  document.querySelectorAll('.section-content').forEach(el=>el.classList.toggle('hidden',Number(el.dataset.section)!==n));document.querySelectorAll('.section-banner').forEach((el,i)=>el.classList.toggle('hidden',i+1!==n));document.querySelectorAll('.section-tab').forEach(el=>el.classList.toggle('active',Number(el.dataset.section)===n));
  renderQuestionNav();syncTranscriptSection(n);const first=(n-1)*10+1;if(sectionForQuestion(currentQuestion)!==n)currentQuestion=first;updateAllIndicators();document.getElementById('questionsPanel').scrollTop=0;
}
function initQuestionNav(){renderQuestionNav()}
function renderQuestionNav(){const nav=document.getElementById('questionNav');nav.innerHTML='';const start=(currentSection-1)*10+1;for(let n=start;n<start+10;n++){const b=document.createElement('button');b.type='button';b.className='subQuestion';b.dataset.question=n;b.textContent=n;b.addEventListener('click',()=>goToQuestion(n));nav.appendChild(b)}}
function anchorForQuestion(n){const g=pickTwoGroups.find(x=>x.questionIds.includes(n));return g?document.getElementById(g.anchor):document.querySelector(`.question-anchor[data-question="${n}"]`)}
function goToQuestion(n){n=Math.max(1,Math.min(40,Number(n)));currentQuestion=n;const s=sectionForQuestion(n);if(s!==currentSection)switchToSection(s);window.setTimeout(()=>{const el=anchorForQuestion(n);if(el)el.scrollIntoView({behavior:'smooth',block:'center'});updateAllIndicators();focusTranscriptEvidence(n)},30)}
function nextQuestion(){goToQuestion(Math.min(40,currentQuestion+1))}function previousQuestion(){goToQuestion(Math.max(1,currentQuestion-1))}
function syncPickTwoGroup(group){
  const inputs=[...document.querySelectorAll('input[name="'+group.name+'"]')],selected=inputs.filter(input=>input.checked),limitReached=selected.length>=group.maxSelections;
  inputs.forEach(input=>{input.disabled=checked||(limitReached&&!input.checked)});
  const count=document.getElementById(group.anchor)?.querySelector('.pick-count');if(count)count.textContent=selected.length+' of '+group.maxSelections+' selected';
}
function handlePickTwoChange(e){
  if(checked)return;const group=pickTwoGroups.find(item=>item.name===e.target.name);if(!group)return;
  let selected=getPickSelections(group);if(selected.length>group.maxSelections){e.target.checked=false;selected=getPickSelections(group)}
  syncPickTwoGroup(group);currentQuestion=group.questionIds[Math.max(0,Math.min(selected.length,group.questionIds.length)-1)]||group.questionIds[0];updateAllIndicators();
}
function syncMapCells(){document.querySelectorAll('.lmap-cell').forEach(c=>c.classList.toggle('selected',c.querySelector('input').checked))}
function getPickSelections(group){return [...document.querySelectorAll(`input[name="${group.name}"]:checked`)].map(x=>x.value)}
function getQuestionAnswer(n){
  const g=pickTwoGroups.find(x=>x.questionIds.includes(Number(n)));if(g)return getPickSelections(g);
  const slot=document.querySelector(`.ldm-slot[data-question="${n}"]`);if(slot)return slot.dataset.answer||'';const text=document.getElementById(`q${n}`);if(text)return text.value.trim();const checkedRadio=document.querySelector(`input[name="q${n}"]:checked`);return checkedRadio?checkedRadio.value:'';
}
function isQuestionAnswered(n){const g=pickTwoGroups.find(x=>x.questionIds.includes(Number(n)));if(g){const idx=g.questionIds.indexOf(Number(n));return getPickSelections(g).length>idx}return String(getQuestionAnswer(n)).trim()!==''}
function getAnsweredCount(){let count=0;for(let n=1;n<=40;n++)if(!pickQuestionIds.has(n)&&isQuestionAnswered(n))count++;pickTwoGroups.forEach(g=>count+=Math.min(g.maxSelections,getPickSelections(g).length));return count}
function updateAllIndicators(){
  document.getElementById('answeredCount').textContent=`${getAnsweredCount()} of 40 answered`;
  document.querySelectorAll('.subQuestion').forEach(btn=>{const n=Number(btn.dataset.question);btn.classList.remove('correct','partial','incorrect');btn.classList.toggle('active',n===currentQuestion);if(!checked)btn.classList.toggle('answered',isQuestionAnswered(n));else if(questionResultStates[n])btn.classList.add(questionResultStates[n])});
}
function updateTimerDisplay(){const el=document.getElementById('timerDisplay');el.textContent=formatTime(timeInSeconds);if(timeInSeconds<=300){el.style.color='#dc3545';el.style.animation='timerBlink 1s steps(1) infinite'}else{el.style.color='';el.style.animation=''}}
function toggleTimer(){if(checked)return;if(timerRunning){clearInterval(timerInterval);timerRunning=false}else{timerRunning=true;timerInterval=setInterval(()=>{timeInSeconds--;updateTimerDisplay();if(timeInSeconds<=0){clearInterval(timerInterval);timerRunning=false;document.getElementById('timerToggle').textContent='▶';checkAnswers()}},1000)}document.getElementById('timerToggle').textContent=timerRunning?'❚❚':'▶'}
function resetTimer(){clearInterval(timerInterval);timerInterval=null;timerRunning=false;timeInSeconds=1800;document.getElementById('timerToggle').textContent='▶';updateTimerDisplay()}
function toggleTheme(){const root=document.documentElement,btn=document.getElementById('themeToggle'),dark=root.getAttribute('data-theme')==='dark';if(dark){root.removeAttribute('data-theme');btn.setAttribute('aria-label','Enable night mode');btn.title='Night mode'}else{root.setAttribute('data-theme','dark');btn.setAttribute('aria-label','Enable day mode');btn.title='Day mode'}btn.querySelector('.theme-moon-icon')?.classList.toggle('hidden',!dark);btn.querySelector('.theme-sun-icon')?.classList.toggle('hidden',dark)}
function setTextSize(size){if(!['small','medium','large'].includes(size))size='medium';currentTextSize=size;document.documentElement.setAttribute('data-text-size',size);document.querySelectorAll('.text-size-control [data-text-size]').forEach(btn=>{const active=btn.dataset.textSize===size;btn.classList.toggle('active',active);btn.setAttribute('aria-pressed',String(active))})}
async function toggleFullscreen(){try{if(!document.fullscreenElement){await document.documentElement.requestFullscreen()}else{await document.exitFullscreen()}}catch(err){console.warn('Fullscreen is unavailable:',err)}}
function syncFullscreenButton(){const btn=document.getElementById('fullscreenBtn');if(!btn)return;const isFullscreen=Boolean(document.fullscreenElement);btn.setAttribute('aria-label',isFullscreen?'Exit fullscreen':'Enter fullscreen');btn.title=isFullscreen?'Exit full screen':'Full screen';btn.querySelector('.fullscreen-enter-icon')?.classList.toggle('hidden',isFullscreen);btn.querySelector('.fullscreen-exit-icon')?.classList.toggle('hidden',!isFullscreen)}
function normalizeAnswerValue(value){let s=String(value??'').toLowerCase().trim();const variants={colour:'color',centre:'center',theatre:'theater',litre:'liter',metre:'meter',organise:'organize',organisation:'organization','mins':'minutes'};s=s.replace(/\$/g,'').replace(/[^a-z0-9\s:]/g,' ').replace(/\s+/g,' ').trim();s=s.split(' ').map(p=>variants[p]||p).join(' ');return s}
function isCorrectValue(user,correct){const u=normalizeAnswerValue(user);return (Array.isArray(correct)?correct:[correct]).some(a=>normalizeAnswerValue(a)===u)}
function displayCorrect(correct){return (Array.isArray(correct)?correct:[correct])[0]}
function clearResultUI(){document.querySelectorAll('.correct-ui,.incorrect-ui').forEach(el=>el.classList.remove('correct-ui','incorrect-ui'));document.querySelectorAll('.correct-answer-display').forEach(el=>el.remove())}
function addCorrectDisplay(target,answer){const span=document.createElement('span');span.className='correct-answer-display';span.innerHTML=`&nbsp;➜&nbsp;<span>${answer}</span>`;target.insertAdjacentElement('afterend',span)}
function gradeNormal(n){
  const answer=correctAnswers[n],user=getQuestionAnswer(n),ok=isCorrectValue(user,answer),slot=document.querySelector('.ldm-slot[data-question="'+n+'"]'),text=document.getElementById('q'+n);
  if(slot){slot.classList.add(ok?'correct-ui':'incorrect-ui');if(!ok)addCorrectDisplay(slot,displayCorrect(answer))}else if(text){text.classList.add(ok?'correct-ui':'incorrect-ui');if(!ok)addCorrectDisplay(text,displayCorrect(answer))}else{const options=[...document.querySelectorAll('input[name="q'+n+'"]')];options.forEach(inp=>{const label=inp.closest('label')||inp.closest('.lmap-cell');if(inp.checked)label.classList.add(ok?'correct-ui':'incorrect-ui');if(!ok&&normalizeAnswerValue(inp.value)===normalizeAnswerValue(displayCorrect(answer)))label.classList.add('correct-ui')})}
  questionResultStates[n]=ok?'correct':'incorrect';const btn=document.querySelector('.subQuestion[data-question="'+n+'"]');if(btn)btn.classList.add(questionResultStates[n]);return{n,user:user||'—',correct:displayCorrect(answer),score:ok?1:0,max:1,status:ok?'✓':'✗'}
}
function gradePickGroup(group){
  const selected=getPickSelections(group),hits=selected.filter(a=>group.correctAnswers.includes(a)).length;
  document.querySelectorAll('input[name="'+group.name+'"]').forEach(inp=>{const label=inp.closest('label');if(group.correctAnswers.includes(inp.value))label.classList.add('correct-ui');else if(inp.checked)label.classList.add('incorrect-ui')});
  group.questionIds.forEach(n=>{questionResultStates[n]=hits===2?'correct':hits===1?'partial':'incorrect';const btn=document.querySelector('.subQuestion[data-question="'+n+'"]');if(btn)btn.classList.add(questionResultStates[n])});
  const block=document.getElementById(group.anchor);if(hits!==group.maxSelections&&block){const target=block.querySelector('.pick-count')||block;addCorrectDisplay(target,group.correctAnswers.join(', '))}
  return{n:group.questionIds[0]+'–'+group.questionIds[1],user:selected.length?selected.join(', '):'—',correct:group.correctAnswers.join(', '),score:hits,max:2,status:hits+'/2',pick:true}
}
function checkAnswers(){
  if(checked){showResultsModal();return}checked=true;clearInterval(timerInterval);timerRunning=false;document.getElementById('timerToggle').textContent='▶';document.querySelectorAll('audio').forEach(a=>a.pause());clearResultUI();document.getElementById('questionsPanel').classList.add('answers-locked');document.querySelectorAll('#questionsPanel input,#questionsPanel select,#questionsPanel textarea').forEach(el=>el.disabled=true);
  const rows=[];let total=0;const sectionScores=[0,0,0,0];for(let n=1;n<=40;n++){if(pickQuestionIds.has(n))continue;const r=gradeNormal(n);rows.push(r);total+=r.score;sectionScores[sectionForQuestion(n)-1]+=r.score}pickTwoGroups.forEach(g=>{const r=gradePickGroup(g);rows.push(r);total+=r.score;sectionScores[sectionForQuestion(g.questionIds[0])-1]+=r.score});rows.sort((a,b)=>parseInt(a.n)-parseInt(b.n));buildResults(rows,total,sectionScores);const btn=document.getElementById('checkButton');btn.disabled=false;btn.classList.add('result-mode');btn.textContent='My Result';enterTranscriptReviewMode();showResultsModal()
}
function calculateBandScore(n){if(n>=39)return'9.0';if(n>=37)return'8.5';if(n>=35)return'8.0';if(n>=32)return'7.5';if(n>=30)return'7.0';if(n>=26)return'6.5';if(n>=23)return'6.0';if(n>=18)return'5.5';if(n>=16)return'5.0';if(n>=13)return'4.5';return'4.0'}
function buildResults(rows,total,sections){document.getElementById('resultsSummary').innerHTML=`<p>Score:<span>${total} / 40</span></p><p>Band:<span>${calculateBandScore(total)}</span></p>${sections.map((s,i)=>`<p>Section ${i+1}:<span>${s}/10</span></p>`).join('')}`;document.getElementById('resultsTable').innerHTML=rows.map(r=>`<div class="result-row ${r.score===r.max?'correct':r.score>0?'partial':'incorrect'} ${r.pick?'pick-two-row':''}" data-score="${r.score}" data-max-score="${r.max}" data-correct="${r.score===r.max?'1':'0'}"><span class="q-num">${r.n}</span><span class="user-ans">${escapeHTML(r.user)}</span><span class="correct-ans">${escapeHTML(r.correct)}</span><span class="result-status" style="color:${r.score===r.max?'#28a745':r.score>0?'#d97706':'#dc3545'}">${r.status}</span></div>`).join('')}
function escapeHTML(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function showResultsModal(){document.getElementById('resultsModal').classList.add('show')}function closeResultsModal(){document.getElementById('resultsModal').classList.remove('show')}
function enterTranscriptReviewMode(){transcriptReviewMode=true;openTranscriptPanel()}
function openTranscriptPanel(){if(!transcriptReviewMode)return;transcriptPanelOpen=true;document.getElementById('mainArea')?.classList.add('transcript-review-mode');document.getElementById('openTranscriptBtn')?.classList.remove('show');syncTranscriptSection(currentSection);focusTranscriptEvidence(currentQuestion)}
function closeTranscriptPanel(){if(!transcriptReviewMode)return;transcriptPanelOpen=false;document.getElementById('mainArea')?.classList.remove('transcript-review-mode');document.getElementById('openTranscriptBtn')?.classList.add('show');document.querySelectorAll('.transcript-answer-hit.transcript-focus').forEach(el=>el.classList.remove('transcript-focus'))}
function syncTranscriptSection(n){document.querySelectorAll('.transcript-section').forEach(section=>section.classList.toggle('active',Number(section.dataset.section)===Number(n)));document.getElementById('transcriptTitle').textContent=`Transcript — Section ${n}`}
function focusTranscriptEvidence(n){if(!transcriptReviewMode||!transcriptPanelOpen)return;const hits=[...document.querySelectorAll(`.transcript-answer-hit[data-questions~="${n}"]`)];document.querySelectorAll('.transcript-answer-hit.transcript-focus').forEach(el=>el.classList.remove('transcript-focus'));if(!hits.length)return;hits.forEach(el=>el.classList.add('transcript-focus'));hits[0].scrollIntoView({behavior:'smooth',block:'center'});setTimeout(()=>hits.forEach(el=>el.classList.remove('transcript-focus')),2200)}
let listeningDragPayload=null;
function listeningTaskFor(element){return element?.closest('.ldm-task')||null}
function listeningTaskIdFor(element){return listeningTaskFor(element)?.dataset.matchTask||''}
function listeningOptionFor(task,code){return task?.querySelector('.ldm-option[data-code="'+code+'"]')||null}
function initListeningDragMatching(){
  document.querySelectorAll('.ldm-option').forEach(option=>{
    option.addEventListener('dragstart',event=>{
      if(checked||option.classList.contains('used')){event.preventDefault();return}
      beginListeningDrag(event,{code:option.dataset.code,label:option.dataset.label,sourceQuestion:null,taskId:listeningTaskIdFor(option),reusable:option.dataset.reusable==='true'},option);
    });
    option.addEventListener('dragend',cleanupListeningDragUI);
    option.addEventListener('click',()=>armListeningMatch(option));
    option.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();event.stopPropagation();armListeningMatch(option)}});
  });
  document.querySelectorAll('.ldm-slot').forEach(slot=>{
    slot.addEventListener('dragstart',event=>{
      const q=Number(slot.dataset.question),value=listeningMatchAssignments[q];
      if(checked||!value){event.preventDefault();return}
      beginListeningDrag(event,{code:value.code,label:value.label,sourceQuestion:q,taskId:listeningTaskIdFor(slot),reusable:value.reusable===true},slot);
    });
    slot.addEventListener('dragend',cleanupListeningDragUI);
    slot.addEventListener('dragover',event=>{const payload=readListeningDrag(event);if(checked||!payload||payload.taskId!==listeningTaskIdFor(slot))return;event.preventDefault();event.dataTransfer.dropEffect=payload.sourceQuestion===null&&payload.reusable?'copy':'move';slot.classList.add('dragover')});
    slot.addEventListener('dragleave',event=>{if(!slot.contains(event.relatedTarget))slot.classList.remove('dragover')});
    slot.addEventListener('drop',event=>{
      if(checked)return;event.preventDefault();const payload=readListeningDrag(event);slot.classList.remove('dragover');if(!payload||payload.taskId!==listeningTaskIdFor(slot))return;
      const targetQuestion=Number(slot.dataset.question);
      if(payload.sourceQuestion!==null&&Number(payload.sourceQuestion)!==targetQuestion)removeListeningAssignment(Number(payload.sourceQuestion));
      if(payload.sourceQuestion===null||Number(payload.sourceQuestion)!==targetQuestion)assignListeningMatch(targetQuestion,payload.code,payload.label,payload.taskId);
      cleanupListeningDragUI();
    });
    const activate=()=>{
      if(checked)return;const q=Number(slot.dataset.question);
      const task=listeningTaskFor(slot),taskId=listeningTaskIdFor(slot);
      if(armedListeningMatch?.taskId===taskId){const option=listeningOptionFor(task,armedListeningMatch.code);if(option)assignListeningMatch(q,armedListeningMatch.code,option.dataset.label,taskId)}
      else if(slot.dataset.answer)clearListeningMatch(q);
    };
    slot.addEventListener('click',activate);
    slot.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();event.stopPropagation();activate()}});
  });
  document.querySelectorAll('.ldm-right').forEach(bank=>{
    bank.addEventListener('dragover',event=>{const payload=readListeningDrag(event);if(checked||!payload||payload.sourceQuestion===null||payload.taskId!==listeningTaskIdFor(bank))return;event.preventDefault();event.dataTransfer.dropEffect='move';bank.classList.add('bank-dragover')});
    bank.addEventListener('dragleave',event=>{if(!bank.contains(event.relatedTarget))bank.classList.remove('bank-dragover')});
    bank.addEventListener('drop',event=>{const payload=readListeningDrag(event);if(checked||!payload||payload.sourceQuestion===null||payload.taskId!==listeningTaskIdFor(bank))return;event.preventDefault();clearListeningMatch(Number(payload.sourceQuestion));cleanupListeningDragUI()});
  });
  syncListeningMatchUI();
}
function beginListeningDrag(event,payload,source){
  listeningDragPayload=payload;source.classList.add('dragging');listeningTaskFor(source)?.classList.add('is-dragging');
  if(event.dataTransfer){event.dataTransfer.effectAllowed=payload.sourceQuestion===null&&payload.reusable?'copyMove':'move';event.dataTransfer.setData('application/x-ielts-match',JSON.stringify(payload));event.dataTransfer.setData('text/plain',payload.code);try{event.dataTransfer.setDragImage(source,24,22)}catch(error){}}
}
function readListeningDrag(event){
  if(listeningDragPayload)return listeningDragPayload;
  if(!event.dataTransfer)return null;
  try{const raw=event.dataTransfer.getData('application/x-ielts-match');if(raw)return JSON.parse(raw)}catch(error){}
  const code=event.dataTransfer.getData('text/plain'),task=listeningTaskFor(event.currentTarget),option=listeningOptionFor(task,code);return code&&option?{code,label:option.dataset.label,sourceQuestion:null,taskId:listeningTaskIdFor(option),reusable:option.dataset.reusable==='true'}:null;
}
function cleanupListeningDragUI(){
  listeningDragPayload=null;document.querySelectorAll('.ldm-task.is-dragging').forEach(task=>task.classList.remove('is-dragging'));
  document.querySelectorAll('.ldm-option.dragging,.ldm-slot.dragging').forEach(element=>element.classList.remove('dragging'));
  document.querySelectorAll('.ldm-slot.dragover').forEach(element=>element.classList.remove('dragover'));
  document.querySelectorAll('.ldm-right.bank-dragover').forEach(element=>element.classList.remove('bank-dragover'));
}
function removeListeningAssignment(q){
  delete listeningMatchAssignments[q];const slot=document.querySelector('.ldm-slot[data-question="'+q+'"]');if(slot){delete slot.dataset.answer;delete slot.dataset.label}
}
function armListeningMatch(option){
  if(checked||!option||option.classList.contains('used'))return;const code=option.dataset.code,taskId=listeningTaskIdFor(option),same=armedListeningMatch?.taskId===taskId&&armedListeningMatch?.code===code;armedListeningMatch=same?null:{taskId,code};syncListeningMatchUI();
}
function assignListeningMatch(q,code,label,taskId){
  if(checked)return;const slot=document.querySelector('.ldm-slot[data-question="'+q+'"]'),task=listeningTaskFor(slot),actualTaskId=listeningTaskIdFor(slot);if(!slot||!task||taskId!==actualTaskId)return;
  const option=listeningOptionFor(task,code),reusable=option?.dataset.reusable==='true',usedBy=Object.entries(listeningMatchAssignments).find(([key,value])=>value.taskId===actualTaskId&&value.code===code&&Number(key)!==Number(q));if(!option||(!reusable&&usedBy))return;
  listeningMatchAssignments[q]={code,label,taskId:actualTaskId,reusable};slot.dataset.answer=code;slot.dataset.label=label;armedListeningMatch=null;currentQuestion=Number(q);syncListeningMatchUI();
}
function clearListeningMatch(q){if(checked)return;removeListeningAssignment(q);currentQuestion=Number(q);armedListeningMatch=null;syncListeningMatchUI()}
function renderListeningSlot(slot,value){
  slot.replaceChildren();
  if(value){
    const code=document.createElement('span'),text=document.createElement('span');code.className='ldm-slot-code';code.textContent=value.code;text.className='ldm-slot-text';text.textContent=value.label;slot.append(code,text);slot.setAttribute('aria-label','Question '+slot.dataset.question+': '+value.code+', '+value.label+'. Click to clear or drag to move.');
  }else{
    const empty=document.createElement('span');empty.className='ldm-slot-empty';empty.textContent='Drop '+(slot.dataset.range||'A–G')+' here';slot.append(empty);slot.setAttribute('aria-label','Question '+slot.dataset.question+': empty answer box.');
  }
}
function syncListeningMatchUI(){
  document.querySelectorAll('.ldm-task').forEach(task=>{
    const taskId=task.dataset.matchTask||'',used=new Set([...task.querySelectorAll('.ldm-slot')].map(slot=>listeningMatchAssignments[slot.dataset.question]?.code).filter(Boolean));
    task.querySelectorAll('.ldm-slot').forEach(slot=>{const value=listeningMatchAssignments[slot.dataset.question];slot.classList.toggle('filled',Boolean(value));slot.draggable=Boolean(value)&&!checked;renderListeningSlot(slot,value)});
    task.querySelectorAll('.ldm-option').forEach(option=>{const reusable=option.dataset.reusable==='true',isUsed=!reusable&&used.has(option.dataset.code),isArmed=armedListeningMatch?.taskId===taskId&&armedListeningMatch?.code===option.dataset.code;option.classList.toggle('used',isUsed);option.classList.toggle('armed',isArmed);option.draggable=!checked&&!isUsed;option.setAttribute('aria-disabled',String(checked||isUsed));option.setAttribute('aria-pressed',String(isArmed))});
  });
  updateAllIndicators();
}
function initHighlighting(){
  const panel=document.getElementById('questionsPanel'),toolbar=document.getElementById('hlToolbar');panel.addEventListener('mouseup',e=>setTimeout(()=>{if(checked&&e.target.closest('input,button,label,.lmap-cell'))return;const sel=window.getSelection();if(sel&&sel.toString().trim()&&sel.rangeCount){const range=sel.getRangeAt(0);if(panel.contains(range.commonAncestorContainer)){savedRange=range.cloneRange();activeHLMark=null;document.getElementById('removeHLButton').classList.add('hidden');positionToolbar(e.clientX,e.clientY)}}},10));panel.addEventListener('click',e=>{const mark=e.target.closest('mark.hl-y');if(mark){activeHLMark=mark;savedRange=null;document.getElementById('removeHLButton').classList.remove('hidden');positionToolbar(e.clientX,e.clientY)}});document.addEventListener('mousedown',e=>{if(!toolbar.contains(e.target)&&!e.target.closest('mark.hl-y'))toolbar.classList.remove('show')})
}
function positionToolbar(x,y){const t=document.getElementById('hlToolbar');t.classList.add('show');requestAnimationFrame(()=>{let lx=x-t.offsetWidth/2,ly=y-t.offsetHeight-14;if(ly<8)ly=y+20;lx=Math.max(8,Math.min(lx,innerWidth-t.offsetWidth-8));t.style.left=`${lx}px`;t.style.top=`${ly}px`})}
function expandRangeToWordBoundaries(range){const r=range.cloneRange();if(r.startContainer.nodeType===3){const t=r.startContainer.textContent;let i=r.startOffset;while(i>0&&/\w/.test(t[i-1]))i--;r.setStart(r.startContainer,i)}if(r.endContainer.nodeType===3){const t=r.endContainer.textContent;let i=r.endOffset;while(i<t.length&&/\w/.test(t[i]))i++;r.setEnd(r.endContainer,i)}return r}
function safeWrapRangeWithMark(range){const r=expandRangeToWordBoundaries(range);if(r.collapsed)return;if(r.startContainer===r.endContainer&&r.startContainer.nodeType===3){const mark=document.createElement('mark');mark.className='hl-y';r.surroundContents(mark);return}const walker=document.createTreeWalker(r.commonAncestorContainer,NodeFilter.SHOW_TEXT);const nodes=[];while(walker.nextNode()){const n=walker.currentNode;try{if(r.intersectsNode(n)&&n.textContent.trim())nodes.push(n)}catch{}}nodes.reverse().forEach(n=>{let start=0,end=n.length;if(n===r.startContainer)start=r.startOffset;if(n===r.endContainer)end=r.endOffset;if(end<=start)return;const rr=document.createRange();rr.setStart(n,start);rr.setEnd(n,end);const m=document.createElement('mark');m.className='hl-y';rr.surroundContents(m)})}
function mergeAdjacentHighlights(root){root.querySelectorAll('mark.hl-y').forEach(mark=>{let next=mark.nextSibling;while(next&&next.nodeType===3&&!next.textContent)next=next.nextSibling;if(next&&next.nodeType===1&&next.matches('mark.hl-y')){while(next.firstChild)mark.appendChild(next.firstChild);next.remove()}})}
function applyHL(){if(activeHLMark){activeHLMark.className='hl-y'}else if(savedRange){safeWrapRangeWithMark(savedRange);mergeAdjacentHighlights(document.getElementById('questionsPanel'))}window.getSelection()?.removeAllRanges();savedRange=null;activeHLMark=null;document.getElementById('hlToolbar').classList.remove('show')}
function removeCurrentHL(){if(activeHLMark){const p=activeHLMark.parentNode;while(activeHLMark.firstChild)p.insertBefore(activeHLMark.firstChild,activeHLMark);activeHLMark.remove();p.normalize()}activeHLMark=null;document.getElementById('hlToolbar').classList.remove('show')}
document.addEventListener('keydown',e=>{const tag=document.activeElement?.tagName;if(['INPUT','TEXTAREA','SELECT'].includes(tag))return;if(e.altKey&&['1','2','3','4'].includes(e.key)){e.preventDefault();switchToSection(Number(e.key))}else if(e.key==='ArrowLeft'){e.preventDefault();previousQuestion()}else if(e.key==='ArrowRight'){e.preventDefault();nextQuestion()}else if(e.code==='Space'){e.preventDefault();toggleTimer()}});
document.addEventListener('DOMContentLoaded',initialize);
</script>
</body>
</html>
