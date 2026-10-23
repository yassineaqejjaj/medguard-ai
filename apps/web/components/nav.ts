import { Activity, FileText, FlaskConical, LayoutGrid, Layers, PlayCircle, ShieldCheck, SlidersHorizontal, UserCheck, type LucideIcon } from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon; later?: boolean };

// Order and labels follow the design's sidebar.
export const NAV: NavItem[] = [
  { href: "/", label: "Overview", icon: LayoutGrid },
  { href: "/systems", label: "AI Systems", icon: Layers },
  { href: "/test-studio", label: "Test Studio", icon: FlaskConical },
  { href: "/runs", label: "Evaluation Runs", icon: PlayCircle },
  { href: "/reviews", label: "Human Reviews", icon: UserCheck },
  { href: "/gates", label: "Release Gates", icon: ShieldCheck },
  { href: "/evidence", label: "Evidence Center", icon: FileText },
  { href: "/monitoring", label: "Monitoring", icon: Activity, later: true },
  { href: "/settings", label: "Settings", icon: SlidersHorizontal },
];

// Screens that exist in the design but are reached from other screens, not the sidebar.
export const EXTRA_ROUTES = ["/compare"];
