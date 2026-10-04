using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class Launcher
{
    [STAThread]
    static void Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, "assistant-env", "Scripts", "pythonw.exe");
        string script = Path.Combine(root, "companion", "web_app.py");
        if (!File.Exists(python) || !File.Exists(script))
        {
            MessageBox.Show("缺少程序文件，请保持启动器、assistant-env 和 companion 在同一个 Pikafish 文件夹中。", "皮卡鱼棋盘助手");
            return;
        }
        try
        {
            ProcessStartInfo start = new ProcessStartInfo(python, "\"" + script + "\"");
            start.WorkingDirectory = root;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            Process.Start(start);
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "皮卡鱼棋盘助手启动失败");
        }
    }
}
