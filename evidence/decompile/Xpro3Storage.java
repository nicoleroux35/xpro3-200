// Decompile the storage-engine entry points and their callers to locate the
// step that should spawn the engine's interrupt-service thread (0x1090C0C).
import java.io.PrintWriter;

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.util.task.ConsoleTaskMonitor;

public class Xpro3Storage extends GhidraScript {

	private static final long[] ENTRIES = {
		0x10913D8L, // contains the real submit site 0x10914F8
		0x1090C0CL, // spawns the engine service thread
		0x1091FBCL, // low-level transfer start used by 0x1092AD0
		0x1093F00L,
	};

	@Override
	protected void run() throws Exception {
		String out = System.getenv("XPRO3_OUT");
		if (out == null) {
			out = "/tmp/opencode";
		}
		String path = out + "/xpro3_storage.txt";
		ConsoleTaskMonitor monitor = new ConsoleTaskMonitor();

		for (long entry : ENTRIES) {
			Address start = toAddr(entry);
			try {
				DisassembleCommand command =
					new DisassembleCommand(new AddressSet(start, toAddr(entry + 0x400)), null, true);
				command.applyTo(currentProgram, monitor);
			} catch (Exception e) {
				println("disassemble failed at " + start);
			}
		}

		DecompInterface decompiler = new DecompInterface();
		decompiler.openProgram(currentProgram);

		try (PrintWriter writer = new PrintWriter(path)) {
			for (long entry : ENTRIES) {
				Address target = toAddr(entry);
				writer.println();
				writer.println("##############################################################################");
				writer.printf("## 0x%08x own body%n", entry);
				writer.println("##############################################################################");
				Function function = getFunctionAt(target);
				if (function == null) {
					function = createFunction(target, null);
				}
				if (function != null) {
					DecompileResults results = decompiler.decompileFunction(function, 150, monitor);
					writer.println(results.decompileCompleted()
						? results.getDecompiledFunction().getC()
						: "(failed: " + results.getErrorMessage() + ")");
				}

				writer.println();
				writer.printf("## callers of 0x%08x%n", entry);
				var references = getReferencesTo(target);
				writer.println("(references: " + references.length + ")");
				for (var reference : references) {
					Address from = reference.getFromAddress();
					writer.printf("%n--- call at 0x%08x ---%n", from.getOffset());
					Function caller = getFunctionContaining(from);
					if (caller == null) {
						try {
							DisassembleCommand command = new DisassembleCommand(
								new AddressSet(from.subtract(0x400), from), null, true);
							command.applyTo(currentProgram, monitor);
						} catch (Exception e) {
							// ignore
						}
						caller = createFunction(from.subtract(0x300), null);
					}
					if (caller == null) {
						writer.println("(no function)");
						continue;
					}
					DecompileResults results = decompiler.decompileFunction(caller, 150, monitor);
					writer.println(results.decompileCompleted()
						? results.getDecompiledFunction().getC()
						: "(failed)");
				}
			}
		}
		println("written " + path);
	}
}