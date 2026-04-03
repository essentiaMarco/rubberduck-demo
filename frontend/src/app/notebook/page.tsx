"use client";

import { useState, useEffect } from "react";

interface Note {
  id: string;
  title: string;
  content: string;
  created_at: string;
  updated_at: string;
  tags: string[];
}

const STORAGE_KEY = "rubberduck_notebook";

export default function NotebookPage() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [selectedNote, setSelectedNote] = useState<Note | null>(null);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");

  // Load from localStorage
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        setNotes(JSON.parse(saved));
      } catch {
        // ignore
      }
    }
  }, []);

  // Save to localStorage
  const saveNotes = (updated: Note[]) => {
    setNotes(updated);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  };

  const createNote = () => {
    const note: Note = {
      id: crypto.randomUUID(),
      title: "Untitled Note",
      content: "",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      tags: [],
    };
    const updated = [note, ...notes];
    saveNotes(updated);
    setSelectedNote(note);
    setEditing(true);
    setEditTitle(note.title);
    setEditContent(note.content);
  };

  const saveEdit = () => {
    if (!selectedNote) return;
    const updated = notes.map((n) =>
      n.id === selectedNote.id
        ? { ...n, title: editTitle, content: editContent, updated_at: new Date().toISOString() }
        : n
    );
    saveNotes(updated);
    const updatedNote = updated.find((n) => n.id === selectedNote.id)!;
    setSelectedNote(updatedNote);
    setEditing(false);
  };

  const deleteNote = (id: string) => {
    const updated = notes.filter((n) => n.id !== id);
    saveNotes(updated);
    if (selectedNote?.id === id) {
      setSelectedNote(null);
      setEditing(false);
    }
  };

  const selectNote = (note: Note) => {
    setSelectedNote(note);
    setEditing(false);
    setEditTitle(note.title);
    setEditContent(note.content);
  };

  const startEdit = () => {
    if (!selectedNote) return;
    setEditTitle(selectedNote.title);
    setEditContent(selectedNote.content);
    setEditing(true);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Investigator Notebook</h1>
        <button
          onClick={createNote}
          className="bg-forensic-accent text-forensic-bg px-4 py-2 rounded text-sm font-medium hover:bg-forensic-accent/90"
        >
          + New Note
        </button>
      </div>

      <div className="flex gap-4 flex-1 min-h-0" style={{ height: "calc(100vh - 180px)" }}>
        {/* Notes list */}
        <div className="w-72 shrink-0 space-y-2 overflow-y-auto pr-2">
          {notes.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-slate-500 text-sm">No notes yet.</p>
              <p className="text-xs text-slate-600 mt-1">Create a note to start documenting your investigation.</p>
            </div>
          ) : (
            notes.map((note) => (
              <div
                key={note.id}
                onClick={() => selectNote(note)}
                className={`rounded-lg border p-3 cursor-pointer transition-colors ${
                  selectedNote?.id === note.id
                    ? "bg-forensic-surface border-forensic-accent"
                    : "bg-forensic-surface border-forensic-border hover:border-slate-600"
                }`}
              >
                <h3 className="text-sm font-medium text-white truncate">{note.title}</h3>
                <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                  {note.content || "Empty note"}
                </p>
                <p className="text-xs text-slate-600 mt-1">
                  {new Date(note.updated_at).toLocaleDateString()}
                </p>
              </div>
            ))
          )}
        </div>

        {/* Note editor / viewer */}
        <div className="flex-1 bg-forensic-surface rounded-lg border border-forensic-border flex flex-col overflow-hidden">
          {selectedNote ? (
            <>
              <div className="flex items-center justify-between px-4 py-3 border-b border-forensic-border">
                {editing ? (
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="flex-1 bg-transparent text-white font-medium focus:outline-none"
                    placeholder="Note title..."
                  />
                ) : (
                  <h2 className="font-medium text-white">{selectedNote.title}</h2>
                )}
                <div className="flex items-center gap-2 ml-3">
                  {editing ? (
                    <>
                      <button
                        onClick={saveEdit}
                        className="text-xs bg-forensic-accent text-forensic-bg px-3 py-1.5 rounded font-medium"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => setEditing(false)}
                        className="text-xs text-slate-400 hover:text-white px-2 py-1.5"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={startEdit}
                        className="text-xs text-slate-400 hover:text-forensic-accent px-2 py-1.5"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => deleteNote(selectedNote.id)}
                        className="text-xs text-red-400 hover:text-red-300 px-2 py-1.5"
                      >
                        Delete
                      </button>
                    </>
                  )}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-4">
                {editing ? (
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    className="w-full h-full bg-transparent text-sm text-slate-300 resize-none focus:outline-none"
                    placeholder="Write your investigation notes here..."
                  />
                ) : (
                  <pre className="text-sm text-slate-300 whitespace-pre-wrap">
                    {selectedNote.content || "Click Edit to start writing."}
                  </pre>
                )}
              </div>

              <div className="px-4 py-2 border-t border-forensic-border text-xs text-slate-600">
                Last updated: {new Date(selectedNote.updated_at).toLocaleString()}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <p className="text-slate-400">Select a note or create a new one</p>
                <p className="text-xs text-slate-600 mt-1">
                  Notes are saved locally in your browser.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
