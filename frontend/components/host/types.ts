export type Option = { id: string; text: string };
export type Question = { id: number; text: string; options: Option[]; correctOptions: string[]; multiple: boolean; image?: string };
export type Participant = { id: number; name: string; score: number; is_online: boolean };
export type HostScreen = 'editor' | 'lobby' | 'question' | 'stats' | 'podium';
