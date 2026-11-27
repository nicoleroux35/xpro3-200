// Find the callers of FUN_01090f70 / FUN_010910b4 / FUN_010907ac and decompile
// them, to identify who passes the progress-callback flag (== 1).
import java.io.PrintWriter;

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.util.task.ConsoleTaskMonitor;

public class Xpro3Entries extends GhidraScript {

	private static final long[] ENTRIES = { 0x1090F70L, 0x10910B4L, 0x10907ACL, 0x1091350L };

	@Override
	protected void run() throws Exception {
		String out = System.getenv("XPRO3_OUT");
		if (out == null) {
			out = "/tmp/opencode";
		}
		String path = out + "/xpro3_entries.txt";
		ConsoleTaskMonitor monitor = new ConsoleTaskMonitor();
		DecompInterface decompiler = new DecompInterface();
		decompiler.openProgram(currentProgram);

		try (PrintWriter writer = new PrintWriter(path)) {
			for (long entry : ENTRIES) {
				Address target = toAddr(entry);
				writer.println();
				writer.println("##############################################################################");
				writer.printf("## callers of 0x%08x%n", entry);
				writer.println("##############################################################################");
				var references = getReferencesTo(target);
				int shown = 0;
				for (var reference : references) {
					Address from = reference.getFromAddress();
					Function caller = getFunctionContaining(from);
					if (caller == null) {
						// disassemble a window before the call so a function can be found
						try {
							DisassembleCommand command = new DisassembleCommand(
								new AddressSet(from.subtract(0x300), from), null, true);
							command.applyTo(currentProgram, monitor);
						} catch (Exception e) {
							// ignore
						}
						caller = createFunction(from.subtract(0x200), null);
					}
					writer.printf("%n--- call at 0x%08x (function %s) ---%n", from.getOffset(),
						caller == null ? "?" : caller.getName());
					if (caller == null) {
						continue;
					}
					DecompileResults results = decompiler.decompileFunction(caller, 120, monitor);
					if (results.decompileCompleted()) {
						writer.println(results.getDecompiledFunction().getC());
						shown++;
					}
					else {
						writer.println("(failed: " + results.getErrorMessage() + ")");
					}
				}
				writer.println();
				writer.println("(callers shown: " + shown + " of " + references.length + ")");
			}
		}
		println("written " + path);
	}
}