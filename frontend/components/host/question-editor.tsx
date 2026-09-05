'use client';
import { Check, ImagePlus, Plus, Trash2, X } from 'lucide-react';
import Image from 'next/image';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { Question } from './types';

const swatches = ['bg-red-500', 'bg-blue-500', 'bg-amber-400', 'bg-emerald-500'];
const shapes = ['▲', '◆', '●', '■'];

export function QuestionEditor({ questions, onChange }: { questions: Question[]; onChange: (items: Question[]) => void }) {
  const add = () => onChange([...questions, { id: Date.now(), text: '', correctOptions: ['a'], multiple: false, options: ['a', 'b', 'c', 'd'].map(id => ({ id, text: '' })) }]);
  const patch = (id: number, value: Partial<Question>) => onChange(questions.map(q => q.id === id ? { ...q, ...value } : q));
  const remove = (id: number) => onChange(questions.filter(q => q.id !== id));
  const setMode = (question: Question, multiple: boolean) => patch(question.id, { multiple, correctOptions: multiple ? question.correctOptions : [question.correctOptions[0] ?? 'a'] });
  const toggleCorrect = (question: Question, optionId: string) => {
    if (!question.multiple) return patch(question.id, { correctOptions: [optionId] });
    const selected = question.correctOptions.includes(optionId);
    if (selected && question.correctOptions.length === 1) return;
    patch(question.id, { correctOptions: selected ? question.correctOptions.filter(id => id !== optionId) : [...question.correctOptions, optionId] });
  };
  const uploadImage = (question: Question, file?: File) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => { if (typeof reader.result === 'string') patch(question.id, { image: reader.result }); };
    reader.readAsDataURL(file);
  };

  return <div className="grid gap-4 xl:grid-cols-2">
    {questions.map((question, index) => <article className="host-card group" key={question.id}>
      <div className="mb-4 flex flex-wrap items-center gap-3"><span className="question-number">{String(index + 1).padStart(2, '0')}</span><div className="choice-mode"><button onClick={() => setMode(question, false)} className={!question.multiple ? 'active' : ''}>Один ответ</button><button onClick={() => setMode(question, true)} className={question.multiple ? 'active' : ''}>Несколько</button></div><button aria-label="Удалить вопрос" onClick={() => remove(question.id)} className="icon-button ml-auto opacity-50 group-hover:opacity-100"><X size={17}/></button></div>
      <Input value={question.text} onChange={e => patch(question.id, { text: e.target.value })} className="host-input mb-3 text-base font-bold" placeholder="Введите вопрос"/>
      {question.image ? <div className="question-image-preview"><Image src={question.image} alt="Иллюстрация вопроса" width={900} height={500} unoptimized/><button onClick={() => patch(question.id, { image: undefined })}><Trash2 size={16}/> Удалить</button></div> : <label className="image-upload"><ImagePlus size={18}/><span>Добавить фото</span><small>PNG, JPG или WEBP</small><input type="file" accept="image/png,image/jpeg,image/webp" onChange={event => uploadImage(question, event.target.files?.[0])}/></label>}
      <div className="mt-3 grid gap-2 sm:grid-cols-2">{question.options.map((option, optionIndex) => { const correct = question.correctOptions.includes(option.id); return <div className={`option-field ${correct ? 'correct' : ''}`} key={option.id}><span className={`option-shape ${swatches[optionIndex]}`}>{shapes[optionIndex]}</span><input value={option.text} onChange={e => patch(question.id, { options: question.options.map(o => o.id === option.id ? { ...o, text: e.target.value } : o) })} placeholder={`Вариант ${optionIndex + 1}`}/><button title="Отметить правильным" onClick={() => toggleCorrect(question, option.id)}>{correct ? <Check size={16}/> : <span className="empty-check"/>}</button></div>})}</div>
      {question.multiple && <p className="multiple-hint">Можно отметить несколько правильных вариантов</p>}
    </article>)}
    <Button onClick={add} variant="outline" className="add-question"><Plus size={24}/> Добавить вопрос</Button>
  </div>;
}
