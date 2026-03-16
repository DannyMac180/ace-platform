defmodule SymphonyElixir.TestSupport.Snapshot do
  import ExUnit.Assertions

  @snapshot_root Path.expand("../fixtures", __DIR__)
  @ansi_regex ~r/\e\[[0-9;]*m/

  @update_snapshot_hint "Run `UPDATE_SNAPSHOTS=1 mix test test/symphony_elixir/status_dashboard_snapshot_test.exs` to create or update fixtures."

  def assert_dashboard_snapshot!(name, raw_ansi_content)
      when is_binary(name) and is_binary(raw_ansi_content) do
    assert_snapshot!(
      Path.join("status_dashboard_snapshots", "#{name}.snapshot.txt"),
      escape_ansi(raw_ansi_content)
    )

    assert_snapshot!(
      Path.join("status_dashboard_snapshots", "#{name}.evidence.md"),
      evidence_markdown(raw_ansi_content)
    )

    :ok
  end

  def assert_snapshot!(relative_path, content)
      when is_binary(relative_path) and is_binary(content) do
    path = snapshot_path(relative_path)
    normalized = normalize_content(content)

    File.mkdir_p!(Path.dirname(path))

    if update_snapshots?() do
      File.write!(path, normalized)
      :ok
    else
      case File.read(path) do
        {:ok, expected} ->
          assert normalized == expected,
                 "Snapshot mismatch for `#{relative_path}`. #{@update_snapshot_hint}"

        {:error, :enoent} ->
          flunk("Missing snapshot fixture `#{relative_path}`. #{@update_snapshot_hint}")

        {:error, reason} ->
          flunk("Failed reading snapshot fixture `#{relative_path}`: #{inspect(reason)}")
      end
    end
  end

  def escape_ansi(content) when is_binary(content), do: String.replace(content, <<27>>, "\\e")

  def strip_ansi(content) when is_binary(content), do: Regex.replace(@ansi_regex, content, "")

  def evidence_markdown(raw_ansi_content) when is_binary(raw_ansi_content) do
    plain =
      raw_ansi_content
      |> strip_ansi()
      |> normalize_content()
      |> String.trim_trailing("\n")

    "```text\n#{plain}\n```\n"
  end

  defp snapshot_path(relative_path), do: Path.join(@snapshot_root, relative_path)

  defp update_snapshots? do
    System.get_env("UPDATE_SNAPSHOTS")
    |> to_string()
    |> String.downcase()
    |> Kernel.in(["1", "true", "yes"])
  end

  defp normalize_content(content) do
    content
    |> String.replace("\r\n", "\n")
    |> String.trim_trailing("\n")
    |> Kernel.<>("\n")
  end
end
