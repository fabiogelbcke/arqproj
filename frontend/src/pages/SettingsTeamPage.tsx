import { useState } from "react";
import { Form, Label, Radio, RadioGroup } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { ApiError } from "../api/client";
import { LIMITS } from "../api/limits";
import { useMe } from "../session/session";
import posthog from "../posthog";
import { useCancelInvite, useInvite, useInviteAgain, useJoinLinkOff, useJoinLinkOn, useTeam, type Member } from "../team/team";
import { Button } from "../ui/Button";
import { DialogFrame } from "../ui/DialogFrame";
import { EmailField } from "../ui/EmailField";
import { ErrorNotice } from "../ui/ErrorNotice";
import { Panel } from "../ui/Panel";
import { TextField } from "../ui/TextField";
import { toast, toastError } from "../ui/Toast";
import styles from "./pages.module.css";


/** A link to pass on, with "Copiar link" (a WhatsApp message, say). */
function LinkToCopy({ link, label }: { link: string; label: string }) {
  const { t } = useTranslation();
  return (
    <div className={styles.linkToCopy}>
      <input aria-label={label} readOnly value={link} onFocus={(event) => event.currentTarget.select()} />
      <Button
        size="small"
        onPress={() =>
          void navigator.clipboard?.writeText(link).then(
            () => toast(t("team.copied")),
            () => toast(link),
          )
        }
      >
        {t("team.copy")}
      </Button>
    </div>
  );
}

/** Configurações → Equipe (A36): who's in, pending invites, and for owners a
 *  personal invite and the shared office link. */
export function SettingsTeamPage() {
  const { t } = useTranslation();
  const team = useTeam();
  if (team.error) return <ErrorNotice error={team.error} />;
  if (!team.data) return <p className={styles.lead}>{t("app.loading")}</p>;
  const manage = team.data.can_manage;
  return (
    <Panel className={styles.settingsPanel} aria-labelledby="team-title">
      <h2 id="team-title" className="sr-only">
        {t("settings.team")}
      </h2>
      {!manage && <p className={styles.small}>{t("team.ownerOnly")}</p>}
      <Members members={team.data.members} manage={manage} />
      {manage && <InviteButton />}
      {manage && <SharedLink on={team.data.join_link.on} until={team.data.join_link.expires_at} />}
    </Panel>
  );
}

function Members({ members, manage }: { members: Member[]; manage: boolean }) {
  const { t } = useTranslation();
  const again = useInviteAgain();
  const cancel = useCancelInvite();
  // The new link for an invite sent again, to copy.
  const [sentAgain, setSentAgain] = useState<{ id: string; link: string; emailed: boolean } | null>(null);
  return (
    <ul className={styles.members} aria-label={t("team.title")}>
      {members.map((member) => (
        <li key={member.id} className={styles.member}>
          <div>
            <strong>
              {member.name}
              {member.me && <span className={styles.small}> {t("team.you")}</span>}
            </strong>
            <span className={styles.small}>{member.email}</span>
          </div>
          <span className={styles.memberRole}>
            {member.status === "invited"
              ? t("team.pending")
              : member.status === "unconfirmed"
                ? t("team.unconfirmed")
                : t(`team.role.${member.role}`)}
          </span>
          {manage && member.status === "invited" && (
            <div className={styles.actions}>
              <Button
                size="small"
                isDisabled={again.isPending}
                onPress={() =>
                  again.mutate(member.id, {
                    onSuccess: (out) => {
                      setSentAgain({ id: member.id, link: out.link, emailed: out.emailed });
                      toast(out.emailed ? t("team.sentAgain", { email: member.email }) : t("team.notEmailed"));
                    },
                    onError: (failure) => toastError(failure),
                  })
                }
              >
                {t("team.sendAgain")}
              </Button>
              <Button
                size="small"
                variant="ghost"
                isDisabled={cancel.isPending}
                onPress={() =>
                  cancel.mutate(member.id, {
                    onSuccess: () => toast(t("team.cancelled", { email: member.email })),
                    onError: (failure) => toastError(failure),
                  })
                }
              >
                {t("team.cancel")}
              </Button>
            </div>
          )}
          {sentAgain?.id === member.id && (
            <LinkToCopy link={sentAgain.link} label={t("team.inviteLinkOf", { name: member.name })} />
          )}
        </li>
      ))}
    </ul>
  );
}

/** "Convidar pessoa" under the team: the invite in a dialog (Fabio, 20 Oct 2026). */
function InviteButton() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.actions}>
      <Button variant="primary" onPress={() => setOpen(true)}>
        {t("team.inviteTitle")}
      </Button>
      {open && <InviteDialog onClose={() => setOpen(false)} />}
    </div>
  );
}

function InviteDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const invite = useInvite();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"member" | "owner">("member");
  const [sent, setSent] = useState<{ email: string; link: string; emailed: boolean } | null>(null);
  const error = invite.error;
  const already =
    error instanceof ApiError && error.code === "already_staff" ? t("team.alreadyIn", { name: error.conflictName }) : null;
  return (
    <DialogFrame title={t("team.inviteTitle")} onClose={onClose}>
      {sent ? (
        // Sent: the link to copy too, then done (or invite someone else).
        <div className={styles.form}>
          <div role="status" className={styles.teamResult}>
            <p>{sent.emailed ? t("team.invited", { email: sent.email }) : t("team.notEmailed")}</p>
            <LinkToCopy link={sent.link} label={t("team.inviteLink")} />
          </div>
          <div className={styles.actions}>
            <Button onPress={() => setSent(null)}>{t("team.inviteAnother")}</Button>
            <Button variant="primary" onPress={onClose}>
              {t("team.done")}
            </Button>
          </div>
        </div>
      ) : (
        <Form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            invite.mutate(
              { name, email, role },
              {
                onSuccess: (out) => {
                  posthog.capture("team_member_invited", { role });
                  setSent({ email: out.member.email, link: out.link, emailed: out.emailed });
                  setName("");
                  setEmail("");
                  setRole("member");
                },
              },
            );
          }}
        >
          <p className={styles.small}>{t("team.inviteIntro")}</p>
          <TextField label={t("team.name")} value={name} onChange={setName} isRequired maxLength={LIMITS.staffName} autoComplete="off" autoFocus />
          <EmailField label={t("team.email")} value={email} onChange={setEmail} isRequired autoComplete="off" />
          <RadioGroup className={styles.roles} value={role} onChange={(value) => setRole(value as "member" | "owner")}>
            <Label className={styles.fieldLabel}>{t("team.roleLabel")}</Label>
            {(["member", "owner"] as const).map((option) => (
              <Radio key={option} value={option} className={styles.roleChoice}>
                <strong>{t(`team.role.${option}`)}</strong>
                <small>{t(`team.roleHint.${option}`)}</small>
              </Radio>
            ))}
          </RadioGroup>
          {already ? (
            <p role="alert" className={styles.problem}>
              {already}
            </p>
          ) : (
            <ErrorNotice error={error} />
          )}
          <div className={styles.actions}>
            <Button onPress={onClose}>{t("team.close")}</Button>
            <Button type="submit" variant="primary" isDisabled={invite.isPending}>
              {invite.isPending ? t("team.inviting") : t("team.invite")}
            </Button>
          </div>
        </Form>
      )}
    </DialogFrame>
  );
}

function SharedLink({ on, until }: { on: boolean; until: string | null | undefined }) {
  const { t, i18n } = useTranslation();
  const me = useMe();
  const turnOn = useJoinLinkOn();
  const turnOff = useJoinLinkOff();
  // Only shown when made: the server keeps just its hash.
  const [link, setLink] = useState<string | null>(null);
  const make = () =>
    turnOn.mutate(undefined, {
      onSuccess: (out) => {
        posthog.capture("team_join_link_enabled", { renewed: on });
        setLink(out.link);
      },
      onError: (failure) => toastError(failure),
    });
  const ends = (iso: string) =>
    // The office's clock, as everywhere in the painel.
    new Intl.DateTimeFormat(i18n.language, {
      timeZone: me.data?.tenant_timezone,
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  return (
    <div className={styles.teamBlock}>
      <h3>{t("team.linkTitle")}</h3>
      <p className={styles.small}>{t("team.linkIntro")}</p>
      {link ? (
        <div role="status" className={styles.teamResult}>
          <LinkToCopy link={link} label={t("team.linkTitle")} />
          <p className={styles.small}>{t("team.linkOnce")}</p>
        </div>
      ) : (
        on && until && <p>{t("team.linkOnUntil", { when: ends(until) })}</p>
      )}
      <div className={styles.actions}>
        <Button onPress={make} isDisabled={turnOn.isPending}>
          {on ? t("team.linkNew") : t("team.linkOn")}
        </Button>
        {on && (
          <Button
            variant="ghost"
            isDisabled={turnOff.isPending}
            onPress={() =>
              turnOff.mutate(undefined, {
                onSuccess: () => {
                  setLink(null);
                  toast(t("team.linkOffDone"));
                },
                onError: (failure) => toastError(failure),
              })
            }
          >
            {t("team.linkOff")}
          </Button>
        )}
      </div>
      {on && <p className={styles.small}>{t("team.linkNewNote")}</p>}
    </div>
  );
}
