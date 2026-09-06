'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import { ArrowLeft, Check, Clock3, LogIn, Trophy, Users, Wifi, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { LanguageSwitch, Locale } from '@/components/language-switch';
import type { Participant } from '@/components/host/types';
import { GameAtmosphere } from './game-atmosphere';

type PlayerQuestion = { id: number; text: string; image?: string; is_multiple?: boolean; duration: number; index?: number; total?: number; options: { id: string; text: string }[] };
type PlayerScreen = 'join' | 'waiting' | 'question' | 'result' | 'finished';
type FeedItem = { id: number; kind: string; name?: string | null };
const WS = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/ws/quiz';
const colors = ['answer-red', 'answer-blue', 'answer-gold', 'answer-green'];
const shapes = ['▲', '◆', '●', '■'];

const copy = {
  ru: { back: 'На главную', joinKicker: 'Войти в игру', joinTitle: 'Готовы проверить себя?', code: 'Код комнаты', name: 'Ваше имя', codePh: '000 000', namePh: 'Например, Алия', join: 'Войти в лобби', connecting: 'Подключаемся…', invalidCode: 'Комната не найдена. Проверьте PIN-код.', wait: 'Ждём ведущего', waitSub: 'Вы в лобби. Вопрос откроется у всех одновременно.', inGame: 'в игре', answer: 'Выберите ответ', multiple: 'Можно выбрать несколько', submit: 'Ответить', sent: 'Ответ принят', sentSub: 'Ждём окончания времени и следующего вопроса.', correct: 'Верно!', wrong: 'Не совсем', points: 'очков', finished: 'Игра завершена', place: 'Ваше место', results: 'Результаты', right: 'верных', inLobby: 'В лобби', live: 'Что происходит', answeredOf: 'ответили', fJoined: 'вошёл в игру', fLeft: 'вышел', fAnswered: 'ответил', noResults: 'Результаты появятся после завершения игры.' },
  en: { back: 'Home', joinKicker: 'Join game', joinTitle: 'Ready to test yourself?', code: 'Room code', name: 'Your name', codePh: '000 000', namePh: 'For example, Alex', join: 'Join lobby', connecting: 'Connecting…', invalidCode: 'Room not found. Check the PIN.', wait: 'Waiting for the host', waitSub: 'You are in the lobby. The question will open for everyone at once.', inGame: 'in game', answer: 'Choose an answer', multiple: 'Select all that apply', submit: 'Submit answer', sent: 'Answer submitted', sentSub: 'Waiting for the timer and the next question.', correct: 'Correct!', wrong: 'Not quite', points: 'points', finished: 'Game over', place: 'Your place', results: 'Results', right: 'correct', inLobby: 'In the lobby', live: 'Live activity', answeredOf: 'answered', fJoined: 'joined', fLeft: 'left', fAnswered: 'answered', noResults: 'Results will appear when the game is over.' },
  kz: { back: 'Басты бет', joinKicker: 'Ойынға кіру', joinTitle: 'Өзіңізді сынауға дайынсыз ба?', code: 'Бөлме коды', name: 'Атыңыз', codePh: '000 000', namePh: 'Мысалы, Алия', join: 'Лоббиге кіру', connecting: 'Қосылуда…', invalidCode: 'Бөлме табылмады. PIN-кодты тексеріңіз.', wait: 'Жүргізушіні күтеміз', waitSub: 'Сіз лоббидесіз. Сұрақ барлығына бір уақытта ашылады.', inGame: 'ойында', answer: 'Жауапты таңдаңыз', multiple: 'Бірнеше жауапты таңдауға болады', submit: 'Жауап беру', sent: 'Жауап қабылданды', sentSub: 'Уақыттың аяқталуын және келесі сұрақты күтеміз.', correct: 'Дұрыс!', wrong: 'Дұрыс емес', points: 'ұпай', finished: 'Ойын аяқталды', place: 'Сіздің орныңыз', results: 'Нәтижелер', right: 'дұрыс', inLobby: 'Лоббиде', live: 'Не болып жатыр', answeredOf: 'жауап берді', fJoined: 'кірді', fLeft: 'шықты', fAnswered: 'жауап берді', noResults: 'Нәтижелер ойын аяқталғаннан кейін шығады.' },
};

function LiveFeed({ items, t }: { items: FeedItem[]; t: Record<string, string> }) {
  if (items.length === 0) return null;
  const verb = (kind: string) => kind === 'answered' ? t.fAnswered : kind === 'left' ? t.fLeft : t.fJoined;
  return <div className="live-feed"><span className="live-feed-title">{t.live}</span>
    {items.map(item => <p key={item.id} className={item.kind === 'left' ? 'left' : ''}><i/><b>{item.name ?? '—'}</b> {verb(item.kind)}</p>)}
  </div>;
}

export function PlayerApp({ locale, onLocale, onExit, initialRoom = '' }: { locale: Locale; onLocale: (v: Locale) => void; onExit: () => void; initialRoom?: string }) {
  const t = copy[locale];
  const [screen, setScreen] = useState<PlayerScreen>('join');
  const [roomCode, setRoomCode] = useState(initialRoom);
  const [name, setName] = useState('');
  const [connected, setConnected] = useState(false);
  const [joining, setJoining] = useState(false);
  const [pinError, setPinError] = useState(false);
  const [joinSuccess, setJoinSuccess] = useState(false);
  const [leavingJoin, setLeavingJoin] = useState(false);
  const [gathering, setGathering] = useState(false);
  const [players, setPlayers] = useState<Participant[]>([]);
  const [board, setBoard] = useState<Participant[]>([]);
  const [answered, setAnswered] = useState(0);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [question, setQuestion] = useState<PlayerQuestion | null>(null);
  const [timeLeft, setTimeLeft] = useState(10);
  const [selected, setSelected] = useState<string[]>([]);
  const [result, setResult] = useState<{ correct: boolean; score: number } | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const playerToken = useRef('');
  const keepAlive = useRef(0);
  const retryTimer = useRef(0);
  const wantJoin = useRef(false);
  const cleanCode = roomCode.replace(/\D/g, '').slice(0, 6);

  useEffect(() => () => { wantJoin.current = false; window.clearInterval(keepAlive.current); window.clearTimeout(retryTimer.current); socket.current?.close(); }, []);
  useEffect(() => {
    if (screen !== 'question') return;
    const timer = window.setInterval(() => setTimeLeft(v => Math.max(0, +(v - .1).toFixed(1))), 100);
    return () => window.clearInterval(timer);
  }, [screen, question]);

  // Прокси рвёт молчащий сокет примерно через 27 секунд, а в ожидании вопроса трафика нет.
  // Держим ping'ом; при обрыве переподключаемся и входим тем же токеном - иначе сервер
  // заводит второго участника, и в лобби появляется «лишний» игрок.
  const connectPlayer = (first: boolean) => {
    window.clearInterval(keepAlive.current);
    window.clearTimeout(retryTimer.current);
    let opened = false;
    const ws = new WebSocket(`${WS}/${cleanCode}/?role=player${playerToken.current ? `&player=${playerToken.current}` : ''}`); socket.current = ws;
    const connectionTimer = window.setTimeout(() => { if (!opened) ws.close(); }, 15000);
    ws.onopen = () => {
      opened = true; window.clearTimeout(connectionTimer); setConnected(true); setJoining(false);
      ws.send(JSON.stringify({ type: 'join_lobby', name: name.trim(), token: playerToken.current }));
      keepAlive.current = window.setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping', t: Date.now() })); }, 10000);
      if (first) { setJoinSuccess(true); window.setTimeout(() => setLeavingJoin(true), 450); window.setTimeout(() => setScreen(current => current === 'join' ? 'waiting' : current), 900); }
    };
    ws.onclose = () => {
      window.clearTimeout(connectionTimer); window.clearInterval(keepAlive.current); setConnected(false); setJoining(false);
      if (first && !opened) { setPinError(false); window.requestAnimationFrame(() => setPinError(true)); return; }
      if (wantJoin.current) retryTimer.current = window.setTimeout(() => connectPlayer(false), 2000);
    };
    ws.onmessage = ({ data }) => {
      const event = JSON.parse(data);
      if (event.type === 'joined') playerToken.current = event.token ?? '';
      // При переподключении сервер присылает полное состояние, а не game_started.
      // Без этой ветки игрок после обрыва оставался на «ожидании», пока все отвечали.
      if (event.type === 'state_sync') {
        if (event.status === 'question' && event.question) {
          setAnswered(event.stats?.answered_count ?? 0);
          setQuestion(event.question);
          setTimeLeft(Math.max(0, Math.round(((event.ends_at ?? 0) - event.server_time) / 100) / 10));
          if (!event.me?.answered) { setSelected([]); setResult(null); setScreen('question'); }
        }
        if (event.status === 'finished') setScreen('finished');
      }
      if (event.participants) setPlayers(event.participants);
      if (event.leaderboard) setBoard(event.leaderboard);
      if (event.feed) setFeed(list => [event.feed as FeedItem, ...list.filter(item => item.id !== event.feed.id)].slice(0, 6));
      if (event.type === 'stats_update') setAnswered(event.answered_count ?? 0);
      if (event.type === 'game_started' || event.type === 'question') { setQuestion(event.question); setSelected([]); setResult(null); setAnswered(0); setTimeLeft(event.question.duration ?? 10); setScreen('question'); }
      if (event.type === 'answer_result' && event.accepted) { setResult({ correct: event.correct, score: event.score }); setScreen('result'); }
      if (event.type === 'question_ended') {
        // Свой результат уже мог прийти - не затираем; не ответившему показываем ноль.
        setTimeLeft(0);
        setResult(current => current ?? { correct: false, score: 0 });
        setScreen(current => current === 'question' ? 'result' : current);
      }
      if (event.type === 'game_finished') setScreen('finished');
    };
  };

  const join = () => {
    if (cleanCode.length !== 6 || !name.trim()) return;
    setJoining(true); setPinError(false);
    wantJoin.current = true;
    connectPlayer(true);
  };
  const submit = (optionIds=selected) => { if (!question || optionIds.length === 0 || timeLeft === 0) return; socket.current?.send(JSON.stringify({ type: 'submit_answer', question_id: question.id, option_id: optionIds[0], option_ids: optionIds })); if (!connected) window.setTimeout(() => { setResult({ correct: false, score: 0 }); setScreen('result'); }, 450); };
  const answer = (optionId: string) => { if (!question || timeLeft === 0) return; if (question.is_multiple) { setSelected(value => value.includes(optionId) ? value.filter(id => id !== optionId) : [...value, optionId]); } else if (selected.length === 0) { setSelected([optionId]); submit([optionId]); } };
  const myPosition = useMemo(() => Math.max(1, [...players].sort((a,b) => b.score-a.score).findIndex(p => p.name === name) + 1), [players, name]);

  if (screen === 'join') return <main className="game-shell relative flex min-h-screen items-center justify-center overflow-hidden p-5"><GameAtmosphere focus={gathering || joining || joinSuccess ? 'stack' : undefined}/><section className={`join-card join-transition relative z-10 w-full max-w-md ${leavingJoin ? 'leaving' : ''}`}><div className="mb-10 flex items-center justify-between"><button className="brand flex items-center gap-2" onClick={onExit}><span className="brand-mark">Q</span> QUIZO</button><LanguageSwitch value={locale} onChange={onLocale}/></div><p className="eyebrow">{t.joinKicker}</p><h1 className="mb-8 mt-2 text-4xl font-black">{t.joinTitle}</h1><label className="field-label" htmlFor="room-code">{t.code}</label><Input id="room-code" value={roomCode} onChange={e => { setRoomCode(e.target.value); setPinError(false); }} aria-invalid={pinError} className={`join-input mb-1 ${pinError ? 'pin-error' : ''}`} placeholder={t.codePh}/>{pinError && <p className="pin-error-message">{t.invalidCode}</p>}<label className="field-label mt-4" htmlFor="player-name">{t.name}</label><Input id="player-name" value={name} onChange={e => setName(e.target.value)} onKeyDown={e => e.key === 'Enter' && join()} className="join-input" placeholder={t.namePh} maxLength={32}/><div className="flex justify-center"><Button onClick={join} onPointerEnter={() => setGathering(true)} onPointerLeave={() => setGathering(false)} onFocus={() => setGathering(true)} onBlur={() => setGathering(false)} disabled={joining || joinSuccess || cleanCode.length !== 6 || !name.trim()} className={`join-submit ${joinSuccess ? 'success' : ''}`}>{joinSuccess ? <Check className="success-check"/> : <>{joining ? t.connecting : t.join}<LogIn className="ml-2"/></>}</Button></div><button onClick={onExit} className="mx-auto mt-5 flex items-center gap-2 text-sm font-bold text-white/40 hover:text-white"><ArrowLeft size={15}/>{t.back}</button></section></main>;
  if (screen === 'waiting') return <PlayerFrame locale={locale} onLocale={onLocale} connected={connected}><section className="player-state-card"><div className="waiting-spinner"/><p className="eyebrow">{roomCode}</p><h1>{t.wait}</h1><p>{t.waitSub}</p><span className="player-count"><Users size={18}/>{Math.max(players.length, 1)} {t.inGame}</span><div className="join-feed">{(players.length ? players : [{ id: 0, name, score: 0, is_online: true }]).map(player => <span key={player.id}><i/> {player.name}</span>)}</div><LiveFeed items={feed} t={t}/></section></PlayerFrame>;
  if (screen === 'question' && question) return <PlayerFrame locale={locale} onLocale={onLocale} connected={connected}><section className="w-full max-w-3xl"><div className="mb-4 flex items-center justify-between gap-2"><span className="round-pill">{question.index ?? 1} / {question.total ?? 1}</span><span className="status-pill"><Clock3 size={16}/>{question.is_multiple ? t.multiple : t.answer}</span><span className="status-pill answered-pill"><Users size={16}/>{answered} / {Math.max(players.length, 1)} {t.answeredOf}</span></div><div className={`question-card relative grid min-h-[210px] items-center gap-5 px-6 py-12 text-center ${question.image ? 'sm:grid-cols-[.8fr_1.2fr] sm:text-left' : ''}`}><div className="timer-ring">{Math.ceil(timeLeft)}</div>{question.image && <Image src={question.image} alt="" width={900} height={500} unoptimized className="question-display-image"/>}<h1 className="text-3xl font-black sm:text-5xl">{question.text}</h1></div><Progress value={timeLeft * 10} className="my-4 h-2 bg-white/10"/><div className="grid gap-3 sm:grid-cols-2">{question.options.map((o,i) => <button key={o.id} onClick={() => answer(o.id)} disabled={(!question.is_multiple && selected.length > 0) || timeLeft === 0} className={`answer ${colors[i]} ${selected.includes(o.id) ? 'selected' : ''} ${!question.is_multiple && selected.length > 0 && !selected.includes(o.id) ? 'dimmed' : ''}`}><span className="shape">{shapes[i]}</span>{o.text}</button>)}</div>{question.is_multiple && <Button onClick={() => submit()} disabled={selected.length === 0 || timeLeft === 0} className="mt-4 h-14 w-full rounded-2xl bg-violet-500 text-lg font-black hover:bg-violet-400"><Check/>{t.submit}</Button>}</section></PlayerFrame>;
  if (screen === 'result') return <PlayerFrame locale={locale} onLocale={onLocale} connected={connected}><section className={`result-card ${result?.correct ? 'is-correct' : ''}`}><span className="result-icon">{result?.correct ? <Check/> : <X/>}</span><p className="eyebrow">{t.sent}</p><h1>{result?.correct ? t.correct : t.wrong}</h1><div className="result-score"><b>{result?.score ?? 0}</b><span>{t.points}</span></div><p>{t.sentSub}</p><span className="player-count"><Users size={18}/>{answered} / {Math.max(players.length, 1)} {t.answeredOf}</span><LiveFeed items={feed} t={t}/></section></PlayerFrame>;
  return <PlayerFrame locale={locale} onLocale={onLocale} connected={connected}><section className="player-state-card"><Trophy size={50} className="text-lime-300"/><p className="eyebrow">{t.finished}</p><h1>#{myPosition}</h1><p>{t.place}</p>{board.length === 0 ? <p>{t.noResults}</p> : <><p className="eyebrow mt-6">{t.results}</p><div className="result-board">{board.map((player, index) => <div key={player.id} className={player.name === name ? 'result-row me' : 'result-row'}><span className="rank">{index + 1}</span><b className="flex-1 truncate">{player.name}</b><small>{player.correct ?? 0} {t.right}</small><strong>{player.score}</strong></div>)}</div></>}</section></PlayerFrame>;
}

function PlayerFrame({ locale, onLocale, connected, children }: { locale: Locale; onLocale: (v: Locale) => void; connected: boolean; children: React.ReactNode }) {
  return <main className="game-shell flex min-h-screen flex-col p-4 sm:p-7"><header className="mx-auto flex w-full max-w-5xl items-center justify-between"><span className="brand flex items-center gap-2"><span className="brand-mark">Q</span> QUIZO</span><div className="flex items-center gap-2"><span className="status-pill"><Wifi size={14}/>{connected ? 'Live' : 'Offline'}</span><LanguageSwitch value={locale} onChange={onLocale}/></div></header><div className="flex flex-1 items-center justify-center py-8">{children}</div></main>;
}
