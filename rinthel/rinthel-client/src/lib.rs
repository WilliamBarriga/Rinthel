//! Biblioteca interna del cliente Ratatui — separa `main.rs` (el binario) de
//! los módulos reusables, así los tests de integración en `tests/` importan
//! `protocol`/`app`/`screens` como cualquier crate en vez de necesitar un
//! truco de `#[path]`.

pub mod app;
pub mod effects;
pub mod protocol;
pub mod screens;
pub mod widgets;
