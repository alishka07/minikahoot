'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import Image from 'next/image';
import { BarChart3, Check, ChevronRight, Crown, Play, Radio, RefreshCw, RotateCcw, Shuffle, Users, Wifi } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { QuestionEditor } from './question-editor';
import { HostScreen, Participant, Question } from './types';
import { GameAtmosphere } from '@/components/player/game-atmosphere';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api';
const WS = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/ws/quiz';
const answerColors = ['answer-red', 'answer-blue', 'answer-gold', 'answer-green'];
const shapes = ['▲', '◆', '●', '■'];
const tabs: { id: HostScreen; label: string }[] = [{ id: 'editor', label: 'Редактор' }, { id: 'lobby', label: 'Лобби' }, { id: 'question', label: 'Вопрос' }, { id: 'stats', label: 'Статистика' }, { id: 'podium', label: 'Подиум' }];

const questionBody = (q: Question, order: number) => JSON.stringify({ order, text: q.text, options: q.options, correct_option: q.correctOptions[0], correct_options: q.correctOptions, is_multiple: q.multiple, image: q.image ?? '' });

const syncQuestions = async (code: string, questions: Question[], synced: Set<number>) => {
  const send = async (url: string, method: string, body?: string) => {
    const response = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body });
    if (!response.ok) throw new Error(`Вопрос не сохранён (${response.status})`);
    return response;
  };
  const live = await Promise.all(questions.filter(q => q.text.trim()).map(async (q, index) => {
    if (synced.has(q.id)) { await send(`${API}/rooms/${code}/questions/${q.id}/`, 'PUT', questionBody(q, index + 1)); return q; }
    const saved = await (await send(`${API}/rooms/${code}/questions/`, 'POST', questionBody(q, index + 1))).json() as { id: number };
    return { ...q, id: saved.id };
  }));
  const keep = new Set(live.map(q => q.id));
  await Promise.all([...synced].filter(id => !keep.has(id)).map(id => send(`${API}/rooms/${code}/questions/${id}/`, 'DELETE')));
  synced.clear(); live.forEach(q => synced.add(q.id));
  return live;
};

export function HostApp({ onExit }: { onExit: () => void }) {
  const [screen, setScreen] = useState<HostScreen>('editor');
  const [quizTitle, setQuizTitle] = useState('');
  const [questions, setQuestions] = useState<Question[]>([]);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [roomCode, setRoomCode] = useState('');
  const [connected, setConnected] = useState(false);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [timeLeft, setTimeLeft] = useState(10);
  const [answered, setAnswered] = useState(0);
  const [answerCounts, setAnswerCounts] = useState<Record<string, number>>({});
  const [completedRounds, setCompletedRounds] = useState(0);
  const [gameFinished, setGameFinished] = useState(false);
  const [lobbyError, setLobbyError] = useState('');
  const [opening, setOpening] = useState(false);
  const socket = useRef<WebSocket | null>(null);
  const hostToken = useRef('');
  const syncedIds = useRef(new Set<number>());
  const liveQuestionsRef = useRef<Question[]>([]);
  const keepAlive = useRef(0);
  const retryTimer = useRef(0);
  const wantRoom = useRef('');
  const current = questions[questionIndex] ?? questions[0];
  const joinUrl = typeof window === 'undefined' ? `http://localhost:3000/?room=${roomCode}` : `${window.location.origin}/?room=${roomCode}`;

  useEffect(() => () => { wantRoom.current = ''; window.clearInterval(keepAlive.current); window.clearTimeout(retryTimer.current); socket.current?.close(); }, []);

  // Молчащий сокет прокси закрывает примерно через 27 секунд, а в лобби трафика нет:
  // держим соединение ping'ом и переподключаемся при обрыве - на входе сервер сам
  // присылает state_sync со списком игроков, так что состояние восстанавливается.
  const connect = (code: string) => new Promise<void>((resolve, reject) => {
    window.clearInterval(keepAlive.current);
    window.clearTimeout(retryTimer.current);
    const ws = new WebSocket(`${WS}/${code}/?role=host&token=${hostToken.current}`); socket.current = ws;
    const timer = window.setTimeout(() => { ws.close(); reject(new Error('Сервер не ответил вовремя')); }, 20000);
    ws.onopen = () => {
      window.clearTimeout(timer); setConnected(true); setLobbyError('');
      keepAlive.current = window.setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping', t: Date.now() })); }, 10000);
      resolve();
    };
    ws.onclose = () => {
      window.clearTimeout(timer); window.clearInterval(keepAlive.current); setConnected(false);
      reject(new Error('Соединение с сервером закрыто'));
      if (wantRoom.current === code) retryTimer.current = window.setTimeout(() => { void connect(code).catch(() => {}); }, 2000);
    };
    ws.onmessage = ({ data }) => {
      const event = JSON.parse(data);
      if (event.participants) setParticipants(event.participants);
      if (event.type === 'state_sync') {
        // То же для ведущего: после обрыва он иначе залипал в лобби при идущей игре.
        if (event.status === 'question' && event.question) {
          const index = liveQuestionsRef.current.findIndex(q => q.id === event.question.id);
          if (index >= 0) setQuestionIndex(index);
          setTimeLeft(Math.max(0, Math.round(((event.ends_at ?? 0) - event.server_time) / 100) / 10));
          setScreen(current => current === 'lobby' || current === 'question' ? 'question' : current);
        }
        if (event.status === 'finished') { setGameFinished(true); setScreen(current => current === 'lobby' ? 'podium' : current); }
      }
      if (event.type === 'game_started') { const index = liveQuestionsRef.current.findIndex(q => q.id === event.question.id); if (index >= 0) setQuestionIndex(index); setTimeLeft(10); setAnswered(0); setAnswerCounts({}); setScreen('question'); }
      if (event.type === 'stats_update') { setAnswered(event.answered_count ?? 0); setAnswerCounts(event.answer_counts ?? {}); }
      if (event.type === 'question_ended') {
        setAnswered(event.answered_count ?? 0); setAnswerCounts(event.answer_counts ?? {}); setTimeLeft(0);
        setCompletedRounds(value => Math.max(value, event.index ?? 1));
        setScreen(current => current === 'question' ? 'stats' : current);
      }
    };
  });
  useEffect(() => {
    if (screen !== 'question') return;
    const timer = window.setInterval(() => setTimeLeft(value => {
      const nextValue = Math.max(0, +(value - .1).toFixed(1));
      if (nextValue === 0) window.setTimeout(() => { setCompletedRounds(value => Math.max(value, questionIndex + 1)); setScreen('stats'); }, 0);
      return nextValue;
    }), 100);
    return () => window.clearInterval(timer);
  }, [screen, questionIndex]);

  const openLobby = async (fresh = false) => {
    const reuse = !fresh && roomCode !== '' && socket.current?.readyState === WebSocket.OPEN;
    setLobbyError('');
    setOpening(true);
    setAnswered(0);
    setAnswerCounts({});
    setCompletedRounds(0);
    setGameFinished(false);
    let liveQuestions = questions;
    try {
      let code = roomCode;
      if (!reuse) {
        // Комнату заводим на сервере до показа лобби: раньше здесь был локальный случайный
        // код, и QR успевал увести игрока в комнату, которой на сервере нет.
        wantRoom.current = '';
        socket.current?.close();
        setParticipants([]);
        syncedIds.current.clear();
        const response = await fetch(`${API}/rooms/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        if (!response.ok) throw new Error(`Не удалось создать комнату (${response.status})`);
        const room = await response.json() as { room_code: string; host_token?: string };
        code = room.room_code;
        hostToken.current = room.host_token ?? '';
      }
      liveQuestions = await syncQuestions(code, questions, syncedIds.current);
      liveQuestionsRef.current = liveQuestions;
      setQuestions(liveQuestions);
      // Лобби открываем только после реально установленного сокета: иначе «Начать игру»
      // уходила в пустоту, а игроки оставались ждать.
      if (!reuse) { wantRoom.current = code; await connect(code); }
      setRoomCode(code);
      setScreen('lobby');
    } catch (error) {
      setConnected(false);
      setLobbyError(error instanceof Error ? error.message : 'Не удалось открыть лобби');
    }
    setOpening(false);
  };
  const start = () => { if (!connected) { setLobbyError('Связь с сервером потеряна — откройте лобби заново.'); return; } setLobbyError(''); setTimeLeft(10); setAnswered(0); setAnswerCounts({}); setGameFinished(false); socket.current?.send(JSON.stringify({ type: 'start_game' })); };
  const next = () => { if (questionIndex + 1 < questions.length) { const nextIndex=questionIndex+1; setQuestionIndex(nextIndex); setTimeLeft(10); setAnswered(0); setAnswerCounts({}); if (connected) socket.current?.send(JSON.stringify({ type: 'show_question', question_id: questions[nextIndex].id })); setScreen('question'); } else { socket.current?.send(JSON.stringify({ type: 'finish_game' })); setGameFinished(true); setScreen('podium'); } };
  const shuffle = () => setQuestions(items => [...items].sort(() => Math.random() - .5));
  const leaders = useMemo(() => [...participants].sort((a, b) => b.score - a.score), [participants]);
  const canLaunch = quizTitle.trim() !== '' && questions.length > 0 && questions.every(question => question.text.trim() && question.options.every(option => option.text.trim()));

  return <main className="game-shell relative min-h-screen overflow-hidden p-4 sm:p-7">
    <GameAtmosphere />
    <div className="relative z-10">
      <HostHeader screen={screen} connected={connected} hasStats={completedRounds > 0 && answered > 0} hasPodium={gameFinished && participants.length > 0} onExit={onExit} onGo={setScreen} />
      {screen === 'editor' && <section className="host-page"><div className="host-heading"><div className="w-full max-w-2xl"><p className="eyebrow">Конструктор игры</p><Input value={quizTitle} onChange={event => setQuizTitle(event.target.value)} className="quiz-title-input" placeholder="Название викторины" /></div><div className="flex flex-wrap gap-3"><Button onClick={shuffle} disabled={questions.length < 2} variant="outline" className="secondary-host-button"><Shuffle /> Перемешать</Button><Button onClick={() => openLobby()} disabled={!canLaunch || opening} className="primary-host-button">{opening ? 'Открываем лобби…' : <>Открыть лобби <ChevronRight /></>}</Button></div></div>{lobbyError && <p className="pin-error-message">{lobbyError}</p>}{questions.length > 0 && <div className="run-order"><span>Порядок запуска</span>{questions.map((_, i) => <b key={i}>{i + 1}</b>)}</div>}<QuestionEditor questions={questions} onChange={setQuestions} /></section>}
      {screen === 'lobby' && <Lobby roomCode={roomCode} joinUrl={joinUrl} participants={participants} error={lobbyError} onStart={start} onRegenerate={() => { if (participants.length === 0 || window.confirm(`В комнате уже ${participants.length} игрок(ов). Новый код создаст другую комнату, и они останутся в прежней. Продолжить?`)) void openLobby(true); }} />}
      {screen === 'question' && current && <QuestionView question={current} index={questionIndex} total={questions.length} timeLeft={timeLeft} answered={answered} totalPlayers={participants.length} />}
      {screen === 'stats' && current && <StatsView question={current} participants={participants} answered={answered} counts={answerCounts} hasResults={completedRounds > 0 && answered > 0} isLast={questionIndex === questions.length - 1} onNext={next} />}
      {screen === 'podium' && <Podium participants={leaders} available={gameFinished && participants.length > 0} onRestart={() => { setQuestionIndex(0); void openLobby(true); }} />}
    </div>
  </main>;
}

function HostHeader({ screen, connected, hasStats, hasPodium, onExit, onGo }: { screen: HostScreen; connected: boolean; hasStats: boolean; hasPodium: boolean; onExit: () => void; onGo: (s: HostScreen) => void }) {
  return <header className="mx-auto flex max-w-7xl flex-wrap items-center gap-4"><button className="brand flex items-center gap-2" onClick={onExit}><span className="brand-mark">Q</span> QUIZO</button><nav className="host-tabs">{tabs.map(tab => { const locked = (tab.id === 'stats' && !hasStats) || (tab.id === 'podium' && !hasPodium); return <button key={tab.id} onClick={() => onGo(tab.id)} className={`${screen === tab.id ? 'active' : ''} ${locked ? 'locked' : ''}`}>{tab.label}{locked && <i />}</button> })}</nav><span className="ml-auto status-pill"><Wifi size={15} />{connected ? 'В эфире' : 'Демо-режим'}</span></header>;
}

function Lobby({ roomCode, joinUrl, participants, error, onStart, onRegenerate }: { roomCode: string; joinUrl: string; participants: Participant[]; error: string; onStart: () => void; onRegenerate: () => void }) {
  return <section className="host-page"><div className="grid gap-6 lg:grid-cols-[360px_1fr]"><div className="qr-card"><div className="flex items-center justify-between gap-3"><p className="eyebrow">Комната готова</p><button onClick={onRegenerate} className="refresh-code" title="Создать новую комнату"><RefreshCw size={15}/> Новый код</button></div><h1 className="mt-2 text-3xl font-black">Сканируйте и входите</h1><div className="qr-wrap"><QRCodeSVG key={roomCode} value={joinUrl} size={210} fgColor="#17171f" /></div><p className="text-center text-sm text-white/50">Код комнаты</p><div className="room-code">{roomCode.slice(0,3)} {roomCode.slice(3)}</div></div><div className="panel flex min-h-[570px] flex-col"><div className="flex items-start justify-between"><div><p className="eyebrow">Открытое лобби</p><h2 className="mt-2 text-4xl font-black">Уже в игре: {participants.filter(p => p.is_online).length}</h2><p className="mt-2 text-white/50">Игроки появятся здесь сразу после подключения.</p></div><Users className="text-violet-300" size={36} /></div><div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3">{participants.map((p, i) => <div className={p.is_online ? 'player-chip' : 'player-chip opacity-45'} key={p.id}><span className={`avatar avatar-${i % 4}`}>{p.name[0]}</span><span className="truncate font-bold">{p.name}</span><span className={p.is_online ? 'online' : 'online offline'} /></div>)}</div><div className="mt-auto flex items-center justify-between gap-4 pt-8">{error ? <span className="pin-error-message">{error}</span> : <span className="flex items-center gap-2 text-sm text-white/45"><Radio size={16} className="text-lime-300" />Ждём остальных</span>}<Button onClick={onStart} className="primary-host-button h-14 px-8"><Play fill="currentColor" /> Начать игру</Button></div></div></div></section>;
}

function QuestionView({ question, index, total, timeLeft, answered, totalPlayers }: { question: Question; index: number; total: number; timeLeft: number; answered: number; totalPlayers: number }) {
  return <section className="mx-auto mt-7 max-w-7xl"><div className="mb-5 flex items-center justify-between"><div className="flex gap-2"><span className="round-pill">Вопрос {index + 1} / {total}</span>{question.multiple && <span className="status-pill">Несколько ответов</span>}</div><span className="status-pill"><Users size={16} /> Ответили {answered} из {totalPlayers}</span></div><div className={`question-card relative grid min-h-[260px] items-center gap-6 px-8 py-14 text-center ${question.image ? 'md:grid-cols-[.8fr_1.2fr] md:text-left' : ''}`}><div className="timer-ring">{Math.ceil(timeLeft)}</div>{question.image && <Image src={question.image} alt="Иллюстрация вопроса" width={900} height={500} unoptimized className="question-display-image"/>}<h1 className="max-w-4xl text-4xl font-black leading-tight sm:text-6xl">{question.text}</h1></div><div className="mt-4 flex items-center gap-4"><Progress value={timeLeft * 10} className="h-2 bg-white/10"/><strong className="w-12 text-right text-lime-300">{timeLeft.toFixed(1)}с</strong></div><div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">{question.options.map((o, i) => <div className={`answer ${answerColors[i]}`} key={o.id}><span className="shape">{shapes[i]}</span>{o.text}</div>)}</div></section>;
}

function StatsView({ question, participants, answered, counts: answerCounts, hasResults, isLast, onNext }: { question: Question; participants: Participant[]; answered: number; counts: Record<string, number>; hasResults: boolean; isLast: boolean; onNext: () => void }) {
  if (!hasResults) return <EmptyResults kind="stats" />;
  const counts = question.options.map(option => answerCounts[option.id] ?? 0);
  const max = Math.max(...counts, 1);
  return <section className="host-page"><div className="host-heading"><div><p className="eyebrow">Результаты вопроса</p><h1>{question.text}</h1><p>Получено {answered} ответов. Правильные варианты подсвечены лаймовым.</p></div><Button onClick={onNext} className="primary-host-button">{isLast ? 'Показать подиум' : 'Следующий вопрос'} <ChevronRight /></Button></div><div className="grid gap-5 lg:grid-cols-[1fr_330px]"><div className="panel"><div className="flex h-[330px] items-end gap-3">{question.options.map((option, i) => { const correct = question.correctOptions.includes(option.id); return <div className="flex h-full flex-1 flex-col justify-end" key={option.id}><div className="mb-2 text-center text-2xl font-black">{counts[i]}</div><div className={`stat-bar ${correct ? 'correct' : ''}`} style={{ height: `${Math.max(18, counts[i] / max * 72)}%` }} /> <div className={`mt-3 rounded-xl p-3 text-center text-sm font-bold ${correct ? 'bg-lime-400 text-zinc-950' : 'bg-white/5 text-white/60'}`}>{correct && <Check className="mx-auto mb-1" size={18} />}{option.text}</div></div>})}</div></div><aside className="panel"><p className="eyebrow">Рейтинг</p><h2 className="mt-2 text-2xl font-black">После вопроса</h2>{[...participants].sort((a,b)=>b.score-a.score).slice(0, 4).map((p, i) => <div className="player-row" key={p.id}><span className="rank">{i + 1}</span><b className="flex-1">{p.name}</b><span className="text-white/45">{p.score}</span></div>)}</aside></div></section>;
}

function Podium({ participants, available, onRestart }: { participants: Participant[]; available: boolean; onRestart: () => void }) {
  if (!available) return <EmptyResults kind="podium" />;
  const top = participants.slice(0, 3); const podiumOrder = [top[1], top[0], top[2]].filter(Boolean);
  return <section className="host-page text-center"><p className="eyebrow">Игра завершена</p><h1 className="mt-3 text-5xl font-black">Подиум</h1><div className="podium">{podiumOrder.map((p, visualIndex) => { const place = visualIndex === 1 ? 1 : visualIndex === 0 ? 2 : 3; return <div className={`podium-person place-${place}`} key={p.id}><span className="podium-avatar">{place === 1 && <Crown size={22} />}{p.name[0]}</span><b>{p.name}</b><strong>{p.score}</strong><div className="podium-block">{place}</div></div>})}</div><div className="mx-auto mt-8 max-w-2xl panel text-left">{participants.slice(3).map((p, i) => <div className="player-row" key={p.id}><span className="rank">{i + 4}</span><b className="flex-1">{p.name}</b><strong>{p.score}</strong></div>)}</div><Button onClick={onRestart} variant="outline" className="secondary-host-button mt-6"><RotateCcw /> Сыграть ещё раз</Button></section>;
}

function EmptyResults({ kind }: { kind: 'stats' | 'podium' }) {
  const isPodium = kind === 'podium';
  return <section className="host-page"><div className="empty-results"><span>{isPodium ? <Crown size={34} /> : <BarChart3 size={34} />}</span><p className="eyebrow">Пока пусто</p><h1>{isPodium ? 'Подиум ещё не сформирован' : 'Статистики пока нет'}</h1><p>{isPodium ? 'Завершите все вопросы — после этого здесь появятся победители и итоговый рейтинг.' : 'Сначала откройте лобби и проведите вопрос. Данные появятся после ответов игроков.'}</p></div></section>;
}
