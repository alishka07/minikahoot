export type Locale = 'ru' | 'en' | 'kz';

export function LanguageSwitch({ value, onChange }: { value: Locale; onChange: (locale: Locale) => void }) {
  return <div className="language-switch" aria-label="Language">
    {(['ru', 'en', 'kz'] as Locale[]).map(locale => <button key={locale} onClick={() => onChange(locale)} className={value === locale ? 'active' : ''}>{locale.toUpperCase()}</button>)}
  </div>;
}
