import { useState } from "react";
import { useRecoilValue } from "recoil";
import { askUserState } from "@chainlit/react-client";
import type { ViewerProps } from "@/lib/chainlit/elements";

type FieldType =
  | "text"
  | "number"
  | "email"
  | "password"
  | "date"
  | "datetime"
  | "textarea"
  | "select"
  | "checkbox";

type SelectOption = string | { value: string; label?: string };

interface FormField {
  id: string;
  label: string;
  input_type: FieldType;
  required?: boolean;
  options?: SelectOption[];
  help?: string;
  default?: unknown;
  placeholder?: string;
  rows?: number;
  min?: number;
  max?: number;
  step?: number;
}

interface DynamicFormProps {
  title?: string;
  description?: string;
  fields?: FormField[];
  submitLabel?: string;
  formId?: string;
}

function normalizeOptions(options?: SelectOption[]) {
  return (options ?? []).map((o) =>
    typeof o === "string"
      ? { value: o, label: o }
      : { value: String(o.value), label: o.label ?? String(o.value) },
  );
}

function initialValues(fields: FormField[]): Record<string, unknown> {
  const init: Record<string, unknown> = {};
  for (const f of fields) {
    if (f.default !== undefined) init[f.id] = f.default;
    else if (f.input_type === "checkbox") init[f.id] = false;
    else init[f.id] = "";
  }
  return init;
}

export function DynamicFormElement({ element }: ViewerProps) {
  const props = ((element as { props?: DynamicFormProps }).props) ?? {};
  const fields = props.fields ?? [];

  const ask = useRecoilValue(askUserState);
  const matched =
    ask?.spec.type === "element" && ask.spec.element_id === element.id
      ? ask
      : undefined;

  const [values, setValues] = useState<Record<string, unknown>>(() => initialValues(fields));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);

  const locked = !matched || submitted;

  const setValue = (id: string, v: unknown) =>
    setValues((prev) => ({ ...prev, [id]: v }));

  const handleSubmit = () => {
    if (!matched) return;
    const newErrors: Record<string, string> = {};
    for (const f of fields) {
      if (f.input_type === "checkbox") continue;
      const isRequired = f.required ?? true;
      if (!isRequired) continue;
      const v = values[f.id];
      if (v === undefined || v === null || v === "") newErrors[f.id] = "Required";
    }
    if (Object.keys(newErrors).length) {
      setErrors(newErrors);
      return;
    }
    setErrors({});
    matched.callback({ submitted: true, ...values });
    setSubmitted(true);
  };

  const renderInput = (f: FormField) => {
    const v = values[f.id];
    const err = errors[f.id];
    const inputCls = `input input-bordered w-full${err ? " input-error" : ""}`;

    switch (f.input_type) {
      case "textarea":
        return (
          <textarea
            className={`textarea textarea-bordered w-full${err ? " textarea-error" : ""}`}
            value={String(v ?? "")}
            onChange={(e) => setValue(f.id, e.target.value)}
            disabled={locked}
            placeholder={f.placeholder}
            rows={f.rows ?? 3}
          />
        );
      case "select": {
        const opts = normalizeOptions(f.options);
        return (
          <select
            className={`select select-bordered w-full${err ? " select-error" : ""}`}
            value={String(v ?? "")}
            onChange={(e) => setValue(f.id, e.target.value)}
            disabled={locked}
          >
            <option value="" disabled>
              {f.placeholder ?? "Select…"}
            </option>
            {opts.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        );
      }
      case "checkbox":
        return (
          <input
            type="checkbox"
            className="checkbox"
            checked={Boolean(v)}
            onChange={(e) => setValue(f.id, e.target.checked)}
            disabled={locked}
          />
        );
      case "number":
        return (
          <input
            type="number"
            className={inputCls}
            value={v === "" || v === undefined ? "" : Number(v)}
            onChange={(e) =>
              setValue(f.id, e.target.value === "" ? "" : Number(e.target.value))
            }
            disabled={locked}
            placeholder={f.placeholder}
            min={f.min}
            max={f.max}
            step={f.step}
          />
        );
      case "date":
      case "datetime":
        return (
          <input
            type={f.input_type === "date" ? "date" : "datetime-local"}
            className={inputCls}
            value={String(v ?? "")}
            onChange={(e) => setValue(f.id, e.target.value)}
            disabled={locked}
          />
        );
      case "email":
      case "password":
      case "text":
      default:
        return (
          <input
            type={f.input_type === "email" ? "email" : f.input_type === "password" ? "password" : "text"}
            className={inputCls}
            value={String(v ?? "")}
            onChange={(e) => setValue(f.id, e.target.value)}
            disabled={locked}
            placeholder={f.placeholder}
          />
        );
    }
  };

  if (!fields.length) return null;

  const submitLabel = submitted ? "Submitted" : props.submitLabel ?? "Submit";

  return (
    <div className="border border-base-300 rounded-lg p-4 my-2 bg-base-200/40 space-y-3 max-w-xl">
      {props.title && (
        <div className="font-medium text-base-content">{props.title}</div>
      )}
      {props.description && (
        <p className="text-sm text-base-content/60">{props.description}</p>
      )}
      <div className="space-y-3">
        {fields.map((f) => {
          const isRequired = f.required ?? true;
          const requiredMark = isRequired ? (
            <span className="text-error ml-0.5">*</span>
          ) : null;
          return (
            <div key={f.id} className="flex flex-col gap-1">
              {f.input_type === "checkbox" ? (
                <label className="flex items-center gap-2 text-sm">
                  {renderInput(f)}
                  <span>
                    {f.label}
                    {requiredMark}
                  </span>
                </label>
              ) : (
                <>
                  <label className="text-sm text-base-content/80">
                    {f.label}
                    {requiredMark}
                  </label>
                  {renderInput(f)}
                </>
              )}
              {f.help && (
                <p className="text-xs text-base-content/50">{f.help}</p>
              )}
              {errors[f.id] && (
                <p className="text-xs text-error">{errors[f.id]}</p>
              )}
            </div>
          );
        })}
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <button
          className="btn btn-primary btn-sm"
          onClick={handleSubmit}
          disabled={locked}
        >
          {submitLabel}
        </button>
      </div>
    </div>
  );
}
