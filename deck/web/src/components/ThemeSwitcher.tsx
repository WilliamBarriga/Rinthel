import { LuMonitor, LuMoon, LuSun, LuZap } from "react-icons/lu";
import { useTheme, type Theme } from "../theme";

const OPTIONS: { value: Theme; icon: typeof LuSun; label: string }[] = [
  { value: "light", icon: LuSun, label: "Claro" },
  { value: "dark", icon: LuMoon, label: "Oscuro" },
  { value: "cyberpunk", icon: LuZap, label: "Cyberpunk" },
  { value: "system", icon: LuMonitor, label: "Sistema" },
];

/** One theme owner; only the available space changes the presentation. */
export function ThemeSwitcher({ expanded = false }: { expanded?: boolean }) {
  const { theme, setTheme, editable } = useTheme();
  if (!editable) return null;
  return (
    <div className={`theme-selector ${expanded ? "theme-selector-expanded" : "theme-selector-compact"}`} role="radiogroup" aria-label="Tema">
      {OPTIONS.map(({ value, icon: Icon, label }, index) => (
        <button key={value} type="button" role="radio" aria-label={label}
          aria-checked={theme === value} tabIndex={theme === value ? 0 : -1}
          onClick={() => setTheme(value)} title={label}
          onKeyDown={event => {
            let next = index;
            if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % OPTIONS.length;
            else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index + OPTIONS.length - 1) % OPTIONS.length;
            else if (event.key === "Home") next = 0;
            else if (event.key === "End") next = OPTIONS.length - 1;
            else return;
            event.preventDefault();
            setTheme(OPTIONS[next].value);
            (event.currentTarget.parentElement?.children[next] as HTMLButtonElement)?.focus();
          }}>
          <Icon aria-hidden="true" />{expanded && <span>{label}</span>}
        </button>
      ))}
    </div>
  );
}
