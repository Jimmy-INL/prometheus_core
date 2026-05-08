// Button types
export type Variant =
  | "primary"
  | "secondary"
  | "accent"
  | "info"
  | "success"
  | "warning"
  | "error"
  | "neutral"
  | "ghost";

export type ButtonSize = "xs" | "sm" | "md" | "lg";

export type ButtonShape = "square" | "circle";

export type IconPosition = "left" | "right";

export type ButtonType = "button" | "submit" | "reset";

// Dropdown menu types
export interface MenuItem {
  label: string;
  shortcut?: string | null;
  identifier: string;
  selectValue: boolean | null;
  subList: DropdownMenuItem[] | null;
  onClick?: () => void;
  disabled?: boolean;
}

export interface DropdownMenuItem {
  type: 'normal' | 'check' | 'radio';
  list: MenuItem[];
}
