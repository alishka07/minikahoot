'use client';
import { useEffect, useState } from 'react';
import { ChevronRight, Gamepad2, LayoutDashboard, LogIn, Sparkles } from 'lucide-react';
import { HostApp } from '@/components/host/host-app';
import { PlayerApp } from '@/components/player/player-app';
import { LanguageSwitch, Locale } from '@/components/language-switch';

type Mode = 'landing' | 'host' | 'player';
const copy = {
  ru: { badge: 'Викторина в реальном времени', kicker: 'Игра начинается здесь', title: 'Создай игру.', accent: 'Зажги аудиторию.', text: 'Соберите викторину или присоединитесь по коду. Вопросы открываются у всех одновременно, а результаты обновляются в реальном времени.', host: 'Я ведущий', hostSub: 'Создать и запустить игру', player: 'Я игрок', playerSub: 'Войти по коду комнаты', live: 'ответа в реальном времени' },
  en: { badge: 'Real-time quiz', kicker: 'The game starts here', title: 'Create a game.', accent: 'Light up the room.', text: 'Build a quiz or join with a room code. Questions open for everyone at once and results update in real time.', host: 'I’m the host', hostSub: 'Create and run a game', player: 'I’m a player', playerSub: 'Join with a room code', live: 'live answers' },
  kz: { badge: 'Нақты уақыттағы викторина', kicker: 'Ойын осы жерден басталады', title: 'Ойын құр.', accent: 'Аудиторияны қызықтыр.', text: 'Викторина құрыңыз немесе бөлме коды арқылы қосылыңыз. Сұрақтар барлығына бір уақытта ашылып, нәтижелер бірден жаңарады.', host: 'Мен жүргізушімін', hostSub: 'Ойын құру және бастау', player: 'Мен ойыншымын', playerSub: 'Бөлме коды арқылы кіру', live: 'нақты уақыттағы жауап' },
};

export default function Home() {
  const [mode, setMode] = useState<Mode>('landing');
  const [locale, setLocale] = useState<Locale>('ru');
  const [initialRoom, setInitialRoom] = useState('');
  useEffect(() => { const room = new URLSearchParams(window.location.search).get('room'); if (room) window.setTimeout(() => { setInitialRoom(room); setMode('player'); }, 0); }, []);
  const t = copy[locale];
  if (mode === 'host') return <HostApp onExit={() => setMode('landing')} />;
  if (mode === 'player') return <PlayerApp locale={locale} onLocale={setLocale} initialRoom={initialRoom} onExit={() => setMode('landing')} />;
  return <main className="game-shell flex min-h-screen flex-col p-5 sm:p-8">
    <header className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4"><span className="brand flex items-center gap-2"><span className="brand-mark">Q</span> QUIZO</span><div className="flex items-center gap-3"><span className="status-pill hidden sm:flex"><Gamepad2 size={16}/>{t.badge}</span><LanguageSwitch value={locale} onChange={setLocale}/></div></header>
    <section className="mx-auto grid w-full max-w-7xl flex-1 items-center gap-12 py-12 lg:grid-cols-[1.1fr_.9fr] lg:py-16"><div><div className="hero-orbit justify-start"><span>▲</span><span>◆</span><span>●</span></div><p className="eyebrow">{t.kicker}</p><h1 className="mt-4 max-w-4xl text-5xl font-black leading-[.95] tracking-[-.05em] sm:text-7xl">{t.title}<br/><span className="text-lime-300">{t.accent}</span></h1><p className="mt-7 max-w-xl text-lg leading-relaxed text-white/60">{t.text}</p><div className="mt-9 grid max-w-2xl gap-3 sm:grid-cols-2"><button onClick={() => setMode('host')} className="home-action primary-action"><LayoutDashboard size={28}/><span className="flex-1"><strong>{t.host}</strong><small>{t.hostSub}</small></span><ChevronRight /></button><button onClick={() => setMode('player')} className="home-action"><LogIn size={28}/><span className="flex-1"><strong>{t.player}</strong><small>{t.playerSub}</small></span><ChevronRight /></button></div></div>
      <div className="landing-preview"><div className="preview-top"><span/><span/><span/></div><iframe className="preview-video" src="/quizo-demo.html" title={t.badge} loading="lazy" tabIndex={-1}/><div className="preview-live"><Sparkles size={18}/><b>24 {t.live}</b></div></div>
    </section>
  </main>;
}
