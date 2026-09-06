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
const WS = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/ws/quiz';
const colors = ['answer-red', 'answer-blue', 'answer-gold', 'answer-green'];
const shapes = ['▲', '◆', '●', '■'];

const copy = {
  ru: { back: 'На главную', joinKicker: 'Войти в игру', joinTitle: 'Готовы проверить себя?', code: 'Код комнаты', name: 'Ваше имя', codePh: '000 000', namePh: 'Например, Алия', join: 'Войти в лобби', connecting: 'Подключаемся…', invalidCode: 'Комната не найдена. Проверьте PIN-код.', wait: 'Ждём ведущего', waitSub: 'Вы в лобби. Вопрос откроется у всех одновременно.', inGame: 'в игре', answer: 'Выберите ответ', multiple: 'Можно выбрать несколько', submit: 'Ответить', sent: 'Ответ принят', sentSub: 'Ждём окончания времени и следующего вопроса.', correct: 'Верно!', wrong: 'Не совсем', points: 'очков', finished: 'Игра завершена', place: 'Ваше место', noResults: 'Результаты появятся после завершения игры.' },
  en: { back: 'Home', joinKicker: 'Join game', joinTitle: 'Ready to test yourself?', code: 'Room code', name: 'Your name', codePh: '000 000', namePh: 'For example, Alex', join: 'Join lobby', connecting: 'Connecting…', invalidCode: 'Room not found. Check the PIN.', wait: 'Waiting for the host', waitSub: 'You are in the lobby. The question will open for everyone at once.', inGame: 'in game', answer: 'Choose an answer', multiple: 'Select all that apply', submit: 'Submit answer', sent: 'Answer submitted', sentSub: 'Waiting for the timer and the next question.', correct: 'Correct!', wrong: 'Not quite', points: 'points', finished: 'Game over', place: 'Your place', noResults: 'Results will appear when the game is over.' },
  kz: { back: 'Басты бет', joinKicker: 'Ойынға кіру', joinTitle: 'Өзіңізді сынауға дайынсыз ба?', code: 'Бөлме коды', name: 'Атыңыз', codePh: '000 000', namePh: 'Мысалы, Алия', join: 'Лоббиге кіру', connecting: 'Қосылуда…', invalidCode: 'Бөлме табылмады. PIN-кодты тексеріңіз.', wait: 'Жүргізушіні күтеміз', waitSub: 'Сіз лоббидесіз. Сұрақ барлығына бір уақытта ашылады.', inGame: 'ойында', answer: 'Жауапты таңдаңыз', multiple: 'Бірнеше жауапты таңдауға болады', submit: 'Жауап беру', sent: 'Жауап қабылданды', sentSub: 'Уақыттың аяқталуын және келесі сұрақты күтеміз.', correct: 'Дұрыс!', wrong: 'Дұрыс емес', points: 'ұпай', finished: 'Ойын аяқталды', place: 'Сіздің орныңыз', noResults: 'Нәтижелер ойын аяқталғаннан кейін шығады.' },
};

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
  const [question, setQuestion] = useState<PlayerQuestion | null>(null);
  const [timeLeft, setTimeLeft] = useState(10);
  const [selected, setSelected] = useState<string[]>([]);
  const [result, setResult] = useState<{ correct: boolean; score: number } | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const cleanCode = roomCode.replace(/\D/g, '').slice(0, 6);

  useEffect(() => () => socket.current?.close(), []);
  useEffect(() => {
    if (screen !== 'question') return;
    const timer = window.setInterval(() => setTimeLeft(v => Math.max(0, +(v - .1).toFixed(1))), 100);
    return () => window.clearInterval(timer);
  }, [screen, question]);

  const join = () => {
    if (cleanCode.length !== 6 || !name.trim()) return;
    setJoining(true); setPinError(false);
    let opened = false;
    const ws = new WebSocket(`${WS}/${cleanCode}/?role=player`); socket.current = ws;
    const connectionTimer = window.setTimeout(() => { if (!opened) ws.close(); }, 15000);
    ws.onopen = () => { opened = true; window.clearTimeout(connectionTimer); setConnected(true); setJoining(false); setJoinSuccess(true); ws.send(JSON.stringify({ type: 'join_lobby', name: name.trim() })); window.setTimeout(() => setLeavingJoin(true), 450); window.setTimeout(() => setScreen('waiting'), 900); };
    ws.onclose = () => { window.clearTimeout(connectionTimer); setConnected(false); setJoining(false); if (!opened) { setPinError(false); window.requestAnimationFrame(() => setPinError(true)); } };
    ws.onmessage = ({ data }) => {
      const event = JSON.parse(data);
      if (event.participants) setPlayers(event.participants);
      if (event.type === 'game_started' || event.type === 'question') { setQuestion(event.question); setSelected([]); setResult(null); setTimeLeft(event.question.duration ?? 10); setScreen('question'); }
      if (event.type === 'answer_result' && event.accepted) { setResult({ correct: event.correct, score: event.score }); setScreen('result'); }
      if (event.type === 'game_finished') setScreen('finished');
    };
  };
  const submit = (optionIds=selected) => { if (!question || optionIds.length === 0 || timeLeft === 0) return; socket.current?.send(JSON.stringify({ type: 'submit_answer', question_id: question.id, option_id: optionIds[0], option_ids: optionIds })); if (!connected) window.setTimeout(() => { setResult({ correct: false, score: 0 }); setScreen('result'); }, 450); };
  const answer = (optionId: string) => { if (!question || timeLeft === 0) return; if (question.is_multiple) { setSelected(value => value.includes(optionId) ? value.filter(id => id !== optionId) : [...value, optionId]); } else if (selected.length === 0) { setSelected([optionId]); submit([optionId]); } };
  const myPosition = useMemo(() => Math.max(1, [...players].sort((a,b) => b.score-a.score).findIndex(p => p.name === name) + 1), [players, name]);

  if (screen === 'join') return <main className="game-shell relative flex min-h-screen items-center justify-center overflow-hidden p-5"><GameAtmosphere focus={gathering || joining || joinSuccess ? 'stack' : undefined}/><section className={`join-card join-transition relative z-10 w-full max-w-md ${leavingJoin ? 'leaving' : ''}`}><div className="mb-10 flex items-center justify-between"><button className="brand flex items-center gap-2" onClick={onExit}><span className="brand-mark">Q</span> QUIZO</button><LanguageSwitch value={locale} onChange={onLocale}/></div><p className="eyebrow">{t.joinKicker}</p><h1 className="mb-8 mt-2 text-4xl font-black">{t.joinTitle}</h1><label className="field-label" htmlFor="room-code">{t.code}</label><Input id="room-code" value={roomCode} onChange={e => { setRoomCode(e.target.value); setPinError(false); }} aria-invalid={pinError} className={`join-input mb-1 ${pinError ? 'pin-error' : ''}`} placeholder={t.codePh}/>{pinError && <p className="pin-error-message">{t.invalidCode}</p>}<label className="field-label mt-4" htmlFor="player-name">{t.name}</label><Input id="player-name" value={name} onChange={e => setName(e.target.value)} onKeyDown={e => e.key === 'Enter' && join()} className="join-input" placeholder={t.namePh} maxLength={32}/><div className="flex justify-center"><Button onClick={join} onPointerEnter={() => setGathering(true)} onPointerLeave={() => setGathering(false)} onFocus={() => setGathering(true)} onBlur={() => setGathering(false)} disabled={joining || joinSuccess || cleanCode.length !== 6 || !name.trim()} className={`join-submit ${joinSuccess ? 'success' : ''}`}>{joinSuccess ? <Check className="success-check"/> : <>{joining ? t.connecting : t.join}<LogIn className="ml-2"/></>}</Button></div><button onClick={onExit} className="mx-auto mt-5 flex items-center gap-2 text-sm font-bold text-white/40 hover:text-white"><ArrowLeft size={15}/>{t.back}</button></section></main>;
  if (screen === 'waiting') return <PlayerFrame locale={locale} onLocale={onLocale} connected={connected}><section className="player-state-card"><div className="waiting-spinner"/><p className="eyebrow">{roomCode}</p><h1>{t.wait}</h1><p>{t.waitSub}</p><span className="player-count"><Users size={18}/>{Math.max(players.length, 1)} {t.inGame}</span><div className="join-feed"><span><i/> {name}</span></div></section></PlayerFrame>;
  if (screen === 'question' && question) return <PlayerFrame locale={locale} onLocale={onLocale} connected={connected}><section className="w-full max-w-3xl"><div className="mb-4 flex items-center justify-between gap-2"><span className="round-pill">{question.index ?? 1} / {question.total ?? 1}</span><span className="status-pill"><Clock3 size={16}/>{question.is_multiple ? t.multiple : t.answer}</span></div><div className={`question-card relative grid min-h-[210px] items-center gap-5 px-6 py-12 text-center ${question.image ? 'sm:grid-cols-[.8fr_1.2fr] sm:text-left' : ''}`}><div className="timer-ring">{Math.ceil(timeLeft)}</div>{question.image && <Image src={question.image} alt="" width={900} height={500} unoptimized className="question-display-image"/>}<h1 className="text-3xl font-black sm:text-5xl">{question.text}</h1></div><Progress value={timeLeft * 10} className="my-4 h-2 bg-white/10"/><div className="grid gap-3 sm:grid-cols-2">{question.options.map((o,i) => <button key={o.id} onClick={() => answer(o.id)} disabled={(!question.is_multiple && selected.length > 0) || timeLeft === 0} className={`answer ${colors[i]} ${selected.includes(o.id) ? 'selected' : ''} ${!question.is_multiple && selected.length > 0 && !selected.includes(o.id) ? 'dimmed' : ''}`}><span className="shape">{shapes[i]}</span>{o.text}</button>)}</div>{question.is_multiple && <Button onClick={() => submit()} disabled={selected.length === 0 || timeLeft === 0} className="mt-4 h-14 w-full rounded-2xl bg-violet-500 text-lg font-black hover:bg-violet-400"><Check/>{t.submit}</Button>}</section></PlayerFrame>;
  if (screen === 'result') return <PlayerFrame locale={locale} onLocale={onLocale} connected={connected}><section className={`result-card ${result?.correct ? 'is-correct' : ''}`}><span className="result-icon">{result?.correct ? <Check/> : <X/>}</span><p className="eyebrow">{t.sent}</p><h1>{result?.correct ? t.correct : t.wrong}</h1><div className="result-score"><b>{result?.score ?? 0}</b><span>{t.points}</span></div><p>{t.sentSub}</p></section></PlayerFrame>;
  return <PlayerFrame locale={locale} onLocale={onLocale} connected={connected}><section className="player-state-card"><Trophy size={50} className="text-lime-300"/><p className="eyebrow">{t.finished}</p><h1>#{myPosition}</h1><p>{t.place}</p>{players.length === 0 && <p>{t.noResults}</p>}</section></PlayerFrame>;
}

function PlayerFrame({ locale, onLocale, connected, children }: { locale: Locale; onLocale: (v: Locale) => void; connected: boolean; children: React.ReactNode }) {
  return <main className="game-shell flex min-h-screen flex-col p-4 sm:p-7"><header className="mx-auto flex w-full max-w-5xl items-center justify-between"><span className="brand flex items-center gap-2"><span className="brand-mark">Q</span> QUIZO</span><div className="flex items-center gap-2"><span className="status-pill"><Wifi size={14}/>{connected ? 'Live' : 'Offline'}</span><LanguageSwitch value={locale} onChange={onLocale}/></div></header><div className="flex flex-1 items-center justify-center py-8">{children}</div></main>;
}
