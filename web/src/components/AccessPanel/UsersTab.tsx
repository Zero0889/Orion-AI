/**
 * UsersTab — CRUD del mapping huella_id ↔ persona.
 *
 * Cada usuario tiene:
 *   · fingerprint_id (0-127, slot del AS608)
 *   · name (lo que se muestra en Telegram y en el reporte diario)
 *   · phone (opcional)
 *   · active (toggle blandito que evita borrar la huella del sensor)
 *
 * Patrón de render igual que las otras tabs: cards en mobile, tabla en
 * desktop. Mutations vienen de `index.tsx` (useCreate/Update/DeleteUser).
 */

import { useMemo, useState } from "react";

import type { AccessUser } from "@/api/rest";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Field, Modal, TextInput } from "@/ui/primitives";

import { AccessEmpty, formatTimestamp, useCreateUser, useDeleteUser, useUpdateUser } from "./index";

interface Props {
  users: AccessUser[];
}

const MAX_SLOT = 127; // AS608 admite 0-127

export function UsersTab({ users }: Props) {
  const [modal, setModal] = useState<
    { mode: "create" } | { mode: "edit"; user: AccessUser } | null
  >(null);

  const sorted = useMemo(
    () => [...users].sort((a, b) => a.fingerprint_id - b.fingerprint_id),
    [users],
  );
  const usedSlots = useMemo(() => new Set(users.map((u) => u.fingerprint_id)), [users]);
  const nextFreeSlot = useMemo(() => {
    for (let i = 0; i <= MAX_SLOT; i++) if (!usedSlots.has(i)) return i;
    return -1;
  }, [usedSlots]);

  return (
    <div className="px-4 sm:px-6 py-4 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-[10px] uppercase tracking-[0.22em] text-text-dim font-mono">
          {users.length}/{MAX_SLOT + 1} slots ocupados
        </div>
        <Button
          variant="primary"
          size="sm"
          icon="plus"
          onClick={() => setModal({ mode: "create" })}
          disabled={nextFreeSlot < 0}
          title={nextFreeSlot < 0 ? "Sensor lleno (128 slots)" : "Enrolar nueva huella"}
        >
          Enrolar huella
        </Button>
      </div>

      {users.length === 0 ? (
        <AccessEmpty
          icon="agents"
          title="Sin usuarios enrolados"
          hint="Tocá «Enrolar huella» para asociar un slot del sensor (0-127) con una persona. El ESP32 lee el slot y Orion lo traduce al nombre."
        />
      ) : (
        <>
          {/* ── Mobile: cards ──────────────────────────────────────── */}
          <div className="md:hidden flex flex-col gap-2">
            {sorted.map((u, i) => (
              <UserCard
                key={u.id}
                user={u}
                idx={i}
                onEdit={() => setModal({ mode: "edit", user: u })}
              />
            ))}
          </div>

          {/* ── Desktop: tabla ─────────────────────────────────────── */}
          <div className="hidden md:block surface-2 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-sunken/60 text-[10px] uppercase tracking-[0.18em] text-text-dim">
                  <th className="px-3 py-2 text-left font-medium w-16">Slot</th>
                  <th className="px-3 py-2 text-left font-medium">Nombre</th>
                  <th className="px-3 py-2 text-left font-medium w-36">Teléfono</th>
                  <th className="px-3 py-2 text-left font-medium w-24">Estado</th>
                  <th className="px-3 py-2 text-left font-medium w-44">Creado</th>
                  <th className="px-3 py-2 text-right font-medium w-32">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((u) => (
                  <UserRow key={u.id} user={u} onEdit={() => setModal({ mode: "edit", user: u })} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {modal?.mode === "create" && (
        <UserFormModal
          mode="create"
          initialSlot={nextFreeSlot}
          usedSlots={usedSlots}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.mode === "edit" && (
        <UserFormModal
          mode="edit"
          user={modal.user}
          usedSlots={usedSlots}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}

/* ── Mobile card ────────────────────────────────────────────────────── */

function UserCard({ user, idx, onEdit }: { user: AccessUser; idx: number; onEdit: () => void }) {
  const del = useDeleteUser();
  const update = useUpdateUser();

  return (
    <div
      className="surface-2 rounded-lg p-3 flex flex-col gap-2 animate-fade-in-up"
      style={{ animationDelay: `${idx * 18}ms` }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[10px] uppercase tracking-[0.16em] text-text-dim font-mono">
            Slot #{String(user.fingerprint_id).padStart(3, "0")}
          </div>
          <div className="text-sm font-semibold text-text truncate">{user.name}</div>
          {user.phone && (
            <div className="text-[11px] text-text-dim font-mono truncate mt-0.5">{user.phone}</div>
          )}
        </div>
        <Badge tone={user.active ? "success" : "inactive"} dot>
          {user.active ? "Activo" : "Pausado"}
        </Badge>
      </div>
      <div className="flex items-center gap-2 pt-1.5 border-t border-white/[0.04]">
        <Button
          size="sm"
          variant="secondary"
          icon={user.active ? "stop" : "play"}
          onClick={() => update.mutate({ id: user.id, body: { active: !user.active } })}
          disabled={update.isPending}
        >
          {user.active ? "Pausar" : "Activar"}
        </Button>
        <Button size="sm" variant="secondary" icon="edit" onClick={onEdit}>
          Editar
        </Button>
        <Button
          size="sm"
          variant="ghost"
          icon="trash"
          onClick={() => {
            if (confirm(`¿Borrar a ${user.name}? El slot #${user.fingerprint_id} queda libre.`))
              del.mutate(user.id);
          }}
          disabled={del.isPending}
          className="ml-auto text-danger hover:bg-danger/10"
        />
      </div>
    </div>
  );
}

/* ── Desktop row ────────────────────────────────────────────────────── */

function UserRow({ user, onEdit }: { user: AccessUser; onEdit: () => void }) {
  const del = useDeleteUser();
  const update = useUpdateUser();

  return (
    <tr className="border-t border-white/[0.04] hover:bg-white/[0.02] transition-colors">
      <td className="px-3 py-2 font-mono text-text-dim tabular-nums">
        #{String(user.fingerprint_id).padStart(3, "0")}
      </td>
      <td className="px-3 py-2 font-medium text-text truncate">{user.name}</td>
      <td className="px-3 py-2 font-mono text-text-dim text-xs">
        {user.phone || <span className="text-muted">—</span>}
      </td>
      <td className="px-3 py-2">
        <Badge tone={user.active ? "success" : "inactive"} dot>
          {user.active ? "Activo" : "Pausado"}
        </Badge>
      </td>
      <td className="px-3 py-2 font-mono text-text-dim text-xs tabular-nums whitespace-nowrap">
        {formatTimestamp(user.created)}
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center justify-end gap-1">
          <button
            onClick={() => update.mutate({ id: user.id, body: { active: !user.active } })}
            disabled={update.isPending}
            title={user.active ? "Pausar" : "Activar"}
            className="h-7 w-7 grid place-items-center rounded-md text-text-dim
                       hover:text-text hover:bg-white/[0.05] transition-colors
                       disabled:opacity-50"
          >
            <Icon name={user.active ? "stop" : "play"} size={14} />
          </button>
          <button
            onClick={onEdit}
            title="Editar"
            className="h-7 w-7 grid place-items-center rounded-md text-text-dim
                       hover:text-text hover:bg-white/[0.05] transition-colors"
          >
            <Icon name="edit" size={14} />
          </button>
          <button
            onClick={() => {
              if (confirm(`¿Borrar a ${user.name}? El slot #${user.fingerprint_id} queda libre.`))
                del.mutate(user.id);
            }}
            disabled={del.isPending}
            title="Borrar"
            className="h-7 w-7 grid place-items-center rounded-md text-text-dim
                       hover:text-danger hover:bg-danger/10 transition-colors
                       disabled:opacity-50"
          >
            <Icon name="trash" size={14} />
          </button>
        </div>
      </td>
    </tr>
  );
}

/* ── Modal de enroll / edit ─────────────────────────────────────────── */

function UserFormModal(
  props:
    | { mode: "create"; initialSlot: number; usedSlots: Set<number>; onClose: () => void }
    | { mode: "edit"; user: AccessUser; usedSlots: Set<number>; onClose: () => void },
) {
  const isEdit = props.mode === "edit";
  const create = useCreateUser();
  const update = useUpdateUser();

  const [slot, setSlot] = useState(isEdit ? props.user.fingerprint_id : props.initialSlot);
  const [name, setName] = useState(isEdit ? props.user.name : "");
  const [phone, setPhone] = useState(isEdit ? props.user.phone : "");
  const [active, setActive] = useState(isEdit ? props.user.active : true);
  const [err, setErr] = useState<string | null>(null);

  const slotConflict = !isEdit && (slot < 0 || slot > MAX_SLOT || props.usedSlots.has(slot));

  function handleSave() {
    setErr(null);
    if (!name.trim()) {
      setErr("El nombre no puede estar vacío.");
      return;
    }
    if (!isEdit) {
      if (slotConflict) {
        setErr(`El slot #${slot} ya está en uso o fuera de rango (0-${MAX_SLOT}).`);
        return;
      }
      create.mutate(
        { fingerprint_id: slot, name: name.trim(), phone: phone.trim() || undefined },
        { onSuccess: () => props.onClose() },
      );
    } else {
      update.mutate(
        {
          id: props.user.id,
          body: { name: name.trim(), phone: phone.trim(), active },
        },
        { onSuccess: () => props.onClose() },
      );
    }
  }

  const busy = create.isPending || update.isPending;

  return (
    <Modal
      open
      onClose={props.onClose}
      eyebrow="Acceso por huella"
      title={isEdit ? `Editar ${props.user.name}` : "Enrolar nueva huella"}
      footer={
        <>
          <Button variant="ghost" onClick={props.onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button variant="primary" icon="check" loading={busy} onClick={handleSave}>
            {isEdit ? "Guardar" : "Enrolar"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {!isEdit && (
          <div className="rounded-md border border-pri/25 bg-pri/[0.06] px-3 py-2 text-[11px] text-text-dim leading-relaxed">
            <span className="text-pri font-medium">Tip:</span> primero registrá la huella en el
            sensor (sketch del ESP32) en el slot indicado abajo. Después acá enlazás ese slot con la
            persona.
          </div>
        )}

        <Field
          label="Slot del sensor"
          hint={isEdit ? "No editable — borrá y re-enrolá si necesitás cambiar" : `0-${MAX_SLOT}`}
          error={slotConflict ? `Slot #${slot} ocupado o fuera de rango.` : undefined}
        >
          <TextInput
            type="number"
            min={0}
            max={MAX_SLOT}
            inputMode="numeric"
            value={slot}
            onChange={(e) => setSlot(parseInt(e.target.value, 10) || 0)}
            disabled={isEdit || busy}
          />
        </Field>

        <Field label="Nombre completo">
          <TextInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Juan Pérez"
            disabled={busy}
            autoFocus
          />
        </Field>

        <Field label="Teléfono" hint="Opcional · sin formato">
          <TextInput
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+51 9XX XXX XXX"
            inputMode="tel"
            disabled={busy}
          />
        </Field>

        {isEdit && (
          <label className="flex items-center gap-3 pt-1 cursor-pointer select-none">
            <input
              type="checkbox"
              className="h-4 w-4 accent-pri"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
              disabled={busy}
            />
            <span className="text-sm text-text">Activo</span>
            <span className="text-[11px] text-text-dim">
              Si lo pausás, las lecturas se loguean como DENIED.
            </span>
          </label>
        )}

        {err && (
          <p className="text-xs text-danger flex items-center gap-1.5">
            <Icon name="alert" size={12} /> {err}
          </p>
        )}
      </div>
    </Modal>
  );
}
