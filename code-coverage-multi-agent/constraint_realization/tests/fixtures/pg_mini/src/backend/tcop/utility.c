case T_AlterTableStmt:
				{
					if (cmd->subtype == AT_DetachPartition)
					{
						if (((PartitionCmd *) cmd->def)->concurrent)
							PreventInTransactionBlock(isTopLevel,
													  "ALTER TABLE ... DETACH CONCURRENTLY");
					}
				}
