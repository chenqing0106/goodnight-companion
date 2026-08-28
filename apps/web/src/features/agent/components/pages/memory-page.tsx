import type { MemoryRuntime } from "../../model/companion-runtime";
import { EmptyCapability, Icon, PageIntro } from "../shared/shared-ui";
import styles from "./memory-page.module.css";

export function MemoryPage({ runtime }: { runtime: MemoryRuntime }) {
  if (runtime.status === "unavailable") {
    return (
      <main data-screen-label="记忆">
        <PageIntro
          eyebrow="Memory"
          title="我记得，但不自作主张。"
          subtitle="每条睡眠偏好都应该能看到来源，也应该随时可以修改或删除。"
        />
        <EmptyCapability
          icon="memory"
          title="记忆还没有接入"
          copy="当前后端没有提供记忆读取和编辑接口，所以这里不会展示示例偏好，也不会产生只保存在浏览器里的修改。"
        />
      </main>
    );
  }

  const editMemory = (id: number, currentBody: string) => {
    const next = window.prompt("修改这条记忆", currentBody);
    if (next?.trim()) runtime.edit(id, next.trim());
  };

  return (
    <main data-screen-label="记忆">
      <PageIntro
        eyebrow="Memory"
        title="我记得，但不自作主张。"
        subtitle="每条偏好都说明来源。你可以随时修改或删除，不需要解释原因。"
      />

      {runtime.items.length === 0 && (
        <div className={styles.emptyState}>这里暂时没有保留的睡眠偏好。</div>
      )}

      {runtime.items.map((memory) => (
        <section className={styles.panelCard} key={memory.id}>
          <div className={styles.listRow}>
            <div className={styles.listIcon}>
              <Icon name="memory" />
            </div>
            <div className={styles.listMain}>
              <strong>{memory.title}</strong>
              <span>{memory.body}</span>
            </div>
          </div>
          <div className={styles.memorySource}>{memory.source}</div>
          <div className={styles.memoryActions}>
            <button
              type="button"
              onClick={() => editMemory(memory.id, memory.body)}
            >
              编辑
            </button>
            <button type="button" onClick={() => runtime.remove(memory.id)}>
              删除
            </button>
          </div>
        </section>
      ))}

      <button className={styles.primaryButton} type="button" onClick={runtime.add}>
        <Icon name="plus" size={15} />
        添加一条偏好
      </button>
    </main>
  );
}
